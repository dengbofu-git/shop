import json
from redis.exceptions import RedisError
from django.db import OperationalError,transaction
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from users.decorators import get_user_from_request
from .models import ReservationPolicy,ReservationPolicyChange
from .reservations import (ReservationError, positive, fingerprint, replay, create_orders, close_order)


def error_response(exc):
    response=JsonResponse({'code':exc.status,'error_code':exc.code,'error':exc.message,**exc.details},status=exc.status)
    if 'retry_after' in exc.details:response['Retry-After']=str(exc.details['retry_after'])
    response['Cache-Control']='no-store'
    return response


def buyer(request,username):
    user,error=get_user_from_request(request)
    if error is not None or not user.is_active:raise ReservationError('UNAUTHENTICATED','请先登录有效账号',401)
    from users.access import account_access
    if user.username!=username or account_access(user)['redirect_url']!='/buyer_dashboard.html':raise ReservationError('FORBIDDEN','只能操作本人的买家订单',403)
    return user


def result(orders):
    data=[{'order_id':o.pk,'total_amount':str(o.total_amount),'carts_count':o.total_count,'status':o.status,
           'expires_at':o.expires_at.isoformat() if o.expires_at else None,
           'payment_exception':o.payment_exception,'pay_url':None} for o in orders]
    return {'code':200,'data':{'orders':data,**(data[0] if len(data)==1 else {}),'split_by_merchant':len(data)>1}}


@never_cache
def submit_order(request,username,cart):
    try:
        user=buyer(request,username)
        try:payload=json.loads(request.body)
        except (ValueError,UnicodeDecodeError):raise ReservationError('INVALID_JSON','请求格式错误',400)
        if not isinstance(payload,dict):raise ReservationError('INVALID_JSON','请求格式错误',400)
        request_id=request.headers.get('Idempotency-Key') or payload.get('request_id')
        # The request fingerprint survives successful cart deletion and lost HTTP responses.
        intent={k:payload.get(k) for k in ('address_id','settlement_type','sku_id','buy_count','sku_list')}
        digest=fingerprint(intent)
        old=replay(user,request_id,digest) if request_id else None
        if old is not None:
            from .cart_cleanup import after_checkout
            if old: after_checkout(old[0].checkout_request_id, cart)
            return JsonResponse(result(old))
        kind=str(payload.get('settlement_type'))
        consumed={}
        if kind=='1':items={positive(payload.get('sku_id')):positive(payload.get('buy_count'))}
        elif kind=='0':
            from carts.state import checkout_snapshot
            from .cart_cleanup import drain_cleanup
            drain_cleanup(user_id=user.pk, conn=cart, force=True)
            selected=payload.get('sku_list')
            if selected is not None and (not isinstance(selected,list) or any(not isinstance(i,dict) for i in selected)):
                raise ReservationError('INVALID_CART','采购车商品格式不正确',400)
            requested=None if not selected else [positive(i.get('id') or i.get('sku_id')) for i in selected]
            if requested is not None and len(requested)!=len(set(requested)):
                raise ReservationError('INVALID_CART','采购车商品重复，请重新加载',400)
            all_items=checkout_snapshot(cart,username)
            ids=None if requested is None else set(requested)
            items={}
            for key,value in all_items.items():
                sid=positive(key.decode() if isinstance(key,bytes) else key)
                row=json.loads(value)
                if not isinstance(row,dict):raise ReservationError('INVALID_CART','采购车已变化',400)
                if row.get('status') is True and (ids is None or sid in ids):items[sid]=positive(row.get('count'));consumed[sid]=row
            if ids and set(items)!=ids:raise ReservationError('CART_CHANGED','采购车已变化，请返回重新选择',409)
        else:raise ReservationError('INVALID_SETTLEMENT','结算类型无效',400)
        orders=create_orders(user,request_id,digest,positive(payload.get('address_id')),items,request.META.get('REMOTE_ADDR'),cart_snapshots=consumed)
        if kind=='0' and orders:
            from .cart_cleanup import after_checkout
            transaction.on_commit(lambda: after_checkout(orders[0].checkout_request_id, cart))
        return JsonResponse(result(orders))
    except ReservationError as exc:return error_response(exc)
    except (ValueError,TypeError,AttributeError):return error_response(ReservationError('INVALID_REQUEST','参数或采购车数据无效',400))
    except OperationalError:return error_response(ReservationError('CHECKOUT_BUSY','库存正在更新，请使用原请求编号重试',409))
    except RedisError:
        return error_response(ReservationError('CART_UNAVAILABLE','采购车暂不可用，请稍后使用原请求编号重试',503))


@never_cache
def cancel_order(request,username):
    if request.method!='POST':return JsonResponse({'code':405,'error':'请使用POST'},status=405)
    try:
        user=buyer(request,username)
        data=json.loads(request.body)
        order=close_order(data.get('order_id'),user.pk)
        return JsonResponse({'code':200,'data':{'order_id':order.pk,'status':order.status},'msg':'订单已取消，预留库存已释放'})
    except ReservationError as exc:return error_response(exc)
    except (ValueError,TypeError,AttributeError):return error_response(ReservationError('INVALID_REQUEST','参数无效',400))


@never_cache
def reservation_policy(request):
    user,error=get_user_from_request(request)
    if error is not None or not user.is_active:return JsonResponse({'code':401,'error':'请先登录'},status=401)
    from users.access import account_access
    if account_access(user)['redirect_url']!='/merchant_dashboard.html':return JsonResponse({'code':403,'error':'仅商家可配置本店规则'},status=403)
    fields=['ttl_seconds','max_unpaid_quantity','max_unpaid_amount','max_stock_percent']
    try:
        if request.method=='PUT':
            from decimal import Decimal,InvalidOperation
            data=json.loads(request.body)
            if not isinstance(data,dict) or set(data)!=set(fields+['change_reason']):raise ValueError()
            if not isinstance(data['change_reason'],str) or not 1<=len(data['change_reason'].strip())<=200:raise ValueError()
            values={k:positive(data[k]) for k in fields if k!='max_unpaid_amount'}
            amount=Decimal(str(data['max_unpaid_amount']))
            if not amount.is_finite() or not Decimal('1')<=amount<=Decimal('10000000') or amount!=amount.quantize(Decimal('.01')):raise ValueError()
            if not 60<=values['ttl_seconds']<=900 or not 1<=values['max_stock_percent']<=100 or values['max_unpaid_quantity']>100000:raise ValueError()
            values['max_unpaid_amount']=amount
            with transaction.atomic():
                from users.models import UserProfile
                UserProfile.objects.select_for_update().get(pk=user.pk)
                policy,_=ReservationPolicy.objects.get_or_create(merchant=user)
                policy=ReservationPolicy.objects.select_for_update().get(pk=policy.pk)
                before={k:format(getattr(policy,k),'.2f') if k=='max_unpaid_amount' else getattr(policy,k) for k in fields}
                for key,value in values.items():setattr(policy,key,value)
                policy.save(update_fields=fields)
                after={k:format(getattr(policy,k),'.2f') if k=='max_unpaid_amount' else getattr(policy,k) for k in fields}
                ReservationPolicyChange.objects.create(merchant=user,actor=user,before=before,after=after,reason=data['change_reason'].strip())
        elif request.method=='GET':policy=ReservationPolicy.objects.filter(merchant=user).first() or ReservationPolicy(merchant=user)
        else:return JsonResponse({'code':405,'error':'方法不允许'},status=405)
        return JsonResponse({'code':200,'data':{k:format(getattr(policy,k),'.2f') if k=='max_unpaid_amount' else getattr(policy,k) for k in fields}})
    except (ValueError,TypeError,AttributeError,ArithmeticError,ReservationError):
        return JsonResponse({'code':400,'error':'规则无效：时限60～900秒，占比1～100%，数量和金额须为正数，且须填写变更依据'},status=400)
