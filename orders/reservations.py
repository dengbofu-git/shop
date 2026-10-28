"""Database-authoritative checkout, reservation budgets and lifecycle transitions."""
import hashlib
import hmac
import json
import re
import uuid
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from goods.models import SKU
from inventory.models import Inventory, InventoryLog
from inventory.services import InventoryService
from users.models import UserProfile, Address
from .models import OrderInfo, OrderGoods, CheckoutRequest, StockHold, ReservationPolicy, CheckoutThrottle


class ReservationError(Exception):
    def __init__(self, code, message, status=409, **details):
        self.code,self.message,self.status,self.details=code,message,status,details
        super().__init__(message)


def positive(value):
    if isinstance(value,bool) or not re.fullmatch(r'[1-9][0-9]{0,8}',str(value)):
        raise ReservationError('INVALID_QUANTITY','数量必须为正整数',400)
    return int(value)


def policy_for(merchant_id):
    return ReservationPolicy.objects.filter(merchant_id=merchant_id).first() or ReservationPolicy(merchant_id=merchant_id)


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def record_attempt(source_ip):
    key=hmac.new(settings.SECRET_KEY.encode(),str(source_ip or 'unknown').encode(),hashlib.sha256).hexdigest()
    now=timezone.now()
    with transaction.atomic():
        CheckoutThrottle.objects.get_or_create(key=key,defaults={'window_start':now})
        bucket=CheckoutThrottle.objects.select_for_update().get(pk=key)
        if bucket.window_start <= now-timedelta(minutes=1):bucket.window_start=now;bucket.attempts=0
        if bucket.attempts >= getattr(settings,'RESERVATION_IP_REQUESTS_PER_MINUTE',30):
            raise ReservationError('CHECKOUT_RATE_LIMITED','请求过于频繁，请稍后重试',429,retry_after=60)
        bucket.attempts+=1;bucket.save(update_fields=['attempts','window_start'])


def replay(user, request_id, digest):
    existing=CheckoutRequest.objects.filter(user=user,request_id=request_id).first()
    if existing:
        if existing.fingerprint!=digest:raise ReservationError('IDEMPOTENCY_CONFLICT','请求编号已用于另一笔结算',409)
        return list(existing.orders.order_by('pk'))


def _log(inv, amount, kind, before, after, order):
    InventoryLog.objects.create(sku_id=inv.sku_id,warehouse_id=inv.warehouse_id,log_type=kind,
        quantity=amount,before_quantity=before,after_quantity=after,remark='订单%s %s'%(order.pk,kind))


def _lock_stock(order):
    # Every lifecycle path uses user -> order -> sorted SKU -> sorted ledger locks.
    ids=sorted(set(order.ordergoods_set.values_list('sku_id',flat=True)))
    skus=list(SKU.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
    ledgers={r.pk:r for r in Inventory.objects.select_for_update().filter(sku_id__in=ids).order_by('pk')}
    return skus,ledgers


def _release_locked(order,reason,now):
    _,ledgers=_lock_stock(order)
    for hold in StockHold.objects.select_for_update().filter(item__order_info=order,state='reserved').order_by('pk'):
        inv=ledgers[hold.inventory_id]
        if inv.reserved_quantity<hold.quantity:raise ReservationError('INVENTORY_INCONSISTENT','库存预留记录不一致，请联系管理员')
        before=inv.available_quantity;inv.reserved_quantity-=hold.quantity
        inv.save(update_fields=['reserved_quantity','available_quantity','updated_time'])
        hold.state='released';hold.released_at=now;hold.save(update_fields=['state','released_at'])
        _log(inv,hold.quantity,'release',before,inv.available_quantity,order)
    order.status=0;order.closed_at=now;order.close_reason=reason
    order.save(update_fields=['status','closed_at','close_reason','updated_time'])


def close_order(order_id, user_id=None, reason='user_cancel', expired_only=False):
    owner=OrderInfo.objects.filter(pk=order_id).values_list('user_profile_id',flat=True).first()
    if owner is None:raise ReservationError('ORDER_NOT_FOUND','订单不存在',404)
    if user_id is not None and owner!=user_id:raise ReservationError('ORDER_NOT_FOUND','订单不存在',404)
    with transaction.atomic():
        UserProfile.objects.select_for_update().get(pk=owner)
        order=OrderInfo.objects.select_for_update().get(pk=order_id)
        if order.status==0:return order
        if expired_only and (not order.reservation_managed or order.status!=1 or order.expires_at>timezone.now()):return order
        if order.status!=1 or order.paid_at:raise ReservationError('ORDER_NOT_CANCELLABLE','当前订单不能取消')
        if order.order_type!='standard':raise ReservationError('ORDER_TYPE_UNSUPPORTED','试单或预售请联系商家处理')
        _release_locked(order,reason,timezone.now())
        return order


def expire_orders(user_id=None,sku_ids=None,limit=500):
    qs=OrderInfo.objects.filter(reservation_managed=True,status=1,expires_at__lte=timezone.now())
    if user_id is not None:qs=qs.filter(user_profile_id=user_id)
    if sku_ids is not None:qs=qs.filter(ordergoods__sku_id__in=sku_ids)
    ids=list(qs.order_by('pk').values_list('pk',flat=True).distinct()[:limit])
    for pk in ids:close_order(pk,reason='expired',expired_only=True)
    return len(ids)


def create_orders(user,request_id,digest,address_id,items,source_ip):
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,64}',str(request_id or '')):
        raise ReservationError('IDEMPOTENCY_KEY_REQUIRED','缺少有效的结算请求编号，请刷新重试',400)
    old=replay(user,request_id,digest)
    if old is not None:return old
    record_attempt(source_ip)
    if not items:raise ReservationError('EMPTY_CART','请选择需要结算的商品',400)
    normalized={positive(k):positive(v) for k,v in items.items()}
    expire_orders(user_id=user.pk)
    expire_orders(sku_ids=list(normalized))
    with transaction.atomic():
        buyer=UserProfile.objects.select_for_update().get(pk=user.pk)
        if not buyer.is_active or buyer.user_type!='customer':raise ReservationError('FORBIDDEN','仅有效买家可以下单',403)
        old=replay(buyer,request_id,digest)
        if old is not None:return old
        address=Address.objects.filter(pk=address_id,user_profile=buyer,is_delete=False).first()
        if not address:raise ReservationError('ADDRESS_NOT_FOUND','收货地址不存在',404)
        now=timezone.now()
        recent=OrderInfo.objects.filter(user_profile=buyer,reservation_managed=True,paid_at__isnull=True,close_reason__in=['user_cancel','expired'],closed_at__gte=now-timedelta(hours=1)).order_by('-closed_at')
        if recent.count()>=3:
            retry=recent.first().closed_at+timedelta(minutes=30)
            if retry>now:raise ReservationError('RESERVATION_COOLDOWN','取消或超时次数过多，暂时停止预留',429,retry_after=int((retry-now).total_seconds()))
        if CheckoutRequest.objects.filter(user=buyer,created_at__gte=now-timedelta(minutes=1)).count()>=5:
            raise ReservationError('CHECKOUT_RATE_LIMITED','下单过于频繁，请稍后重试',429,retry_after=60)
        skus=list(SKU.objects.select_for_update().filter(pk__in=normalized).order_by('pk'))
        if len(skus)!=len(normalized):raise ReservationError('SKU_NOT_FOUND','部分商品已不存在',404)
        groups=defaultdict(list);rows_by_sku={}
        for sku in skus:
            spu=sku.spu;merchant=spu.merchant
            if not sku.is_launched or merchant is None or not merchant.is_active:
                raise ReservationError('PRODUCT_UNAVAILABLE','部分商品已下架或商家不可用',409,sku_id=sku.pk)
            rows_by_sku[sku.pk]=InventoryService.locked_ledgers(sku)
            groups[merchant.pk].append(sku)
        pending=OrderInfo.objects.filter(user_profile=buyer,status=1)
        policies={mid:policy_for(mid) for mid in groups}
        window=now-timedelta(hours=1)
        budget=0
        history=OrderInfo.objects.filter(user_profile=buyer,reservation_managed=True).filter(
            Q(status=1)|Q(close_reason__in=['user_cancel','expired'],closed_at__gte=window,paid_at__isnull=True))
        for prior_order in history:
            start=max(prior_order.created_time,window)
            # Active holds include their remaining committed time. Closed holds
            # retain the time actually occupied, even after hiding or cancellation.
            end=prior_order.expires_at if prior_order.status==1 else min(prior_order.closed_at,prior_order.expires_at,now)
            budget+=max(0,(end-start).total_seconds())
        projected=budget+sum(policies[mid].ttl_seconds for mid in groups)
        if projected>getattr(settings,'RESERVATION_MAX_HOLD_SECONDS_PER_HOUR',1800):
            raise ReservationError('RESERVATION_TIME_BUDGET','本小时累计预留时长已达限额，请先处理已有订单或稍后重试',429,retry_after=60)
        if pending.count()+len(groups)>getattr(settings,'RESERVATION_MAX_UNPAID_ORDERS',3):
            raise ReservationError('UNPAID_ORDER_LIMIT','请先付款或取消已有待付款订单',429)
        global_quantity=sum(normalized.values())+(pending.aggregate(total=Sum('total_count'))['total'] or 0)
        if global_quantity>getattr(settings,'RESERVATION_MAX_UNPAID_QUANTITY',300):
            raise ReservationError('UNPAID_QUANTITY_LIMIT','累计待付预留数量超过限额，请先处理已有订单',429)
        global_amount=sum((s.price*normalized[s.pk] for s in skus),Decimal('0'))+(pending.aggregate(total=Sum('total_amount'))['total'] or 0)
        if global_amount>Decimal(str(getattr(settings,'RESERVATION_MAX_UNPAID_AMOUNT',60000))):
            raise ReservationError('UNPAID_AMOUNT_LIMIT','累计待付预留金额超过限额，请先处理已有订单',429)
        for merchant_id,products in groups.items():
            policy=policies[merchant_id]
            prior=OrderGoods.objects.filter(order_info__user_profile=buyer,order_info__status=1,merchant_snapshot_id=merchant_id)
            quantity=sum(normalized[s.pk] for s in products)+sum(prior.values_list('count',flat=True))
            amount=sum((s.price*normalized[s.pk] for s in products),Decimal('0'))+sum((i.price*i.count for i in prior),Decimal('0'))
            if quantity>policy.max_unpaid_quantity or amount>policy.max_unpaid_amount:
                raise ReservationError('BULK_CONFIRMATION_REQUIRED','超过本店待付预留额度，请先联系商家确认采购',409,merchant_id=merchant_id,sku_id=products[0].pk)
            for sku in products:
                if prior.filter(sku=sku).exists():raise ReservationError('SKU_ALREADY_RESERVED','已有该商品的待付款订单，请前往付款或取消',409,sku_id=sku.pk)
                rows=rows_by_sku[sku.pk]
                available=sum(r.available_quantity for r in rows if r.warehouse.is_active)
                count=normalized[sku.pk]
                if available<count:raise ReservationError('INSUFFICIENT_STOCK','商品可售库存不足',409,sku_id=sku.pk,available=available)
                physical=sum(r.quantity for r in rows if r.warehouse.is_active)
                if count*100>physical*policy.max_stock_percent:
                    raise ReservationError('BULK_CONFIRMATION_REQUIRED','采购数量占库存比例较高，请先联系商家确认',409,sku_id=sku.pk,merchant_id=merchant_id)
                if sku.price<=0:raise ReservationError('INVALID_PRICE','商品价格无效，请联系商家',409)
        checkout=CheckoutRequest.objects.create(user=buyer,request_id=request_id,fingerprint=digest)
        result=[]
        for merchant_id,products in sorted(groups.items()):
            expiry=now+timedelta(seconds=policies[merchant_id].ttl_seconds)
            order=OrderInfo.objects.create(user_profile=buyer,order_id=uuid.uuid4().hex,total_amount=sum((s.price*normalized[s.pk] for s in products),Decimal('0')),
                total_count=sum(normalized[s.pk] for s in products),freight=0,pay_method=1,status=1,reservation_managed=True,expires_at=expiry,checkout_request=checkout,
                receiver=address.receiver,address=address.address,receiver_mobile=address.receiver_mobile,tag=address.tag)
            for sku in products:
                count=normalized[sku.pk]
                item=OrderGoods.objects.create(order_info=order,sku=sku,count=count,price=sku.price)
                remain=count
                for inv in rows_by_sku[sku.pk]:
                    if not inv.warehouse.is_active:continue
                    take=min(inv.available_quantity,remain)
                    if not take:continue
                    before=inv.available_quantity;inv.reserved_quantity+=take
                    inv.save(update_fields=['reserved_quantity','available_quantity','updated_time'])
                    StockHold.objects.create(item=item,inventory=inv,quantity=take)
                    _log(inv,take,'reserve',before,inv.available_quantity,order)
                    remain-=take
                if remain:raise ReservationError('INSUFFICIENT_STOCK','库存已变化，请重试')
                InventoryService.sync_stock(sku)
            result.append(order)
        return result


def confirm_payment(order_id,trade_no,amount):
    owner=OrderInfo.objects.filter(pk=order_id).values_list('user_profile_id',flat=True).first()
    if owner is None:raise ReservationError('ORDER_NOT_FOUND','订单不存在',404)
    with transaction.atomic():
        UserProfile.objects.select_for_update().get(pk=owner)
        order=OrderInfo.objects.select_for_update().get(pk=order_id)
        if amount!=order.total_amount:raise ReservationError('PAYMENT_AMOUNT_MISMATCH','支付金额不匹配',400)
        if order.payment_trade_no:
            if order.payment_trade_no!=trade_no:raise ReservationError('PAYMENT_CONFLICT','订单支付流水不匹配',400)
            return order
        now=timezone.now()
        if not order.reservation_managed:
            order.payment_exception='legacy_payment_review'
        elif order.status==0 or order.expires_at<=now:
            if order.status==1:_release_locked(order,'expired',now)
            order.payment_exception='late_payment_refund_required'
        elif order.status!=1:
            raise ReservationError('PAYMENT_STATE_CONFLICT','订单状态不支持支付确认')
        else:
            holds=StockHold.objects.select_for_update().filter(item__order_info=order,state='reserved')
            if (holds.aggregate(total=Sum('quantity'))['total'] or 0)!=order.total_count:
                raise ReservationError('INVENTORY_INCONSISTENT','订单预留不完整，需人工核验')
            holds.update(state='paid');order.status=2
        order.payment_trade_no=trade_no;order.paid_at=now
        order.save(update_fields=['status','paid_at','payment_trade_no','payment_exception','updated_time'])
        return order


def _shipment_state(order,lock=False):
    if order.order_type=='standard':return order,2,3
    if order.reservation_managed:return None,0,0
    from .models import TrialOrder,PreSaleOrder
    model=TrialOrder if order.order_type=='trial' else PreSaleOrder if order.order_type=='presale' else None
    if model is None:return None,0,0
    query=model.objects.filter(order_info=order)
    if lock:query=query.select_for_update()
    detail=query.first()
    if detail is None:return None,0,0
    if order.order_type=='presale' and not (detail.deposit_paid and detail.balance_paid):return None,0,0
    return (detail,2,3) if order.order_type=='trial' else (detail,4,5)


def merchant_actions(order,merchant,items=None):
    items=list(order.ordergoods_set.select_related('sku__spu')) if items is None else items
    owned=bool(items) and all((i.merchant_snapshot_id or i.sku.spu.merchant_id)==merchant.pk for i in items)
    detail,ready,_=_shipment_state(order)
    return {'can_ship':bool(owned and detail is not None and detail.status==ready and not order.payment_exception),
            'can_cancel':bool(owned and order.order_type=='standard' and order.status==1 and not order.paid_at and not order.payment_exception)}


def cancel_by_merchant(order_id,merchant):
    owner=OrderInfo.objects.filter(pk=order_id).values_list('user_profile_id',flat=True).first()
    if owner is None:raise ReservationError('ORDER_NOT_FOUND','订单不存在',404)
    with transaction.atomic():
        UserProfile.objects.select_for_update().get(pk=owner)
        order=OrderInfo.objects.select_for_update().get(pk=order_id)
        items=list(order.ordergoods_set.select_related('sku__spu'))
        if not items or any((i.merchant_snapshot_id or i.sku.spu.merchant_id)!=merchant.pk for i in items):
            raise ReservationError('FORBIDDEN','混合商家订单或其他店铺订单不能整单取消',403)
        if order.order_type!='standard':raise ReservationError('ORDER_TYPE_REQUIRES_REVIEW','试单／预售不能通过普通取消入口处理')
        if order.status==0:return order
        return close_order(order.pk,reason='merchant_cancel')


def ship_order(order_id,merchant):
    owner=OrderInfo.objects.filter(pk=order_id).values_list('user_profile_id',flat=True).first()
    if owner is None:raise ReservationError('ORDER_NOT_FOUND','订单不存在',404)
    with transaction.atomic():
        UserProfile.objects.select_for_update().get(pk=owner)
        order=OrderInfo.objects.select_for_update().get(pk=order_id)
        items=list(order.ordergoods_set.select_related('sku__spu').order_by('sku_id'))
        if not items or any((i.merchant_snapshot_id or i.sku.spu.merchant_id)!=merchant.pk for i in items):
            raise ReservationError('FORBIDDEN','订单含其他商家商品，不能整单发货',403)
        detail,ready,shipped=_shipment_state(order,lock=True)
        if detail is None or order.payment_exception:raise ReservationError('ORDER_NOT_SHIPPABLE','子订单或付款状态未通过核验，不能发货')
        if detail.status==shipped:return order
        if detail.status!=ready:raise ReservationError('ORDER_NOT_SHIPPABLE','当前订单不能发货')
        skus,ledgers=_lock_stock(order)
        if order.reservation_managed:
            holds=list(StockHold.objects.select_for_update().filter(item__order_info=order).order_by('pk'))
            if sum(h.quantity for h in holds)!=order.total_count or any(h.state!='paid' for h in holds):
                raise ReservationError('INVENTORY_INCONSISTENT','已付预留不完整，不能出库')
            for hold in holds:
                inv=ledgers[hold.inventory_id];before=inv.quantity
                if inv.reserved_quantity<hold.quantity:raise ReservationError('INVENTORY_INCONSISTENT','库存账本不一致')
                inv.quantity-=hold.quantity;inv.reserved_quantity-=hold.quantity
                inv.save(update_fields=['quantity','reserved_quantity','available_quantity','updated_time'])
                hold.state='consumed';hold.save(update_fields=['state'])
                _log(inv,hold.quantity,'out',before,inv.quantity,order)
            for sku in skus:InventoryService.sync_stock(sku)
        else:
            for item in items:InventoryService.ship_deduct_sku(item.sku_id,item.count,order_id=order.pk)
        detail.status=shipped
        if detail is order:order.save(update_fields=['status','updated_time'])
        else:
            detail.save(update_fields=['status'])
            order.save(update_fields=['updated_time'])
        return order
