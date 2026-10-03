import datetime
import json
import logging
import random
from datetime import datetime

from alipay import AliPay

logger = logging.getLogger(__name__)
from django.conf import settings
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.views import View
from django_redis import get_redis_connection

from django.db import transaction
from goods.models import SKU
from users.models import UserProfile, Address
from dadashop.utils import jwt_decode
from .models import OrderInfo, OrderGoods


def build_single_data(sku_object, number, status):
    # 获取到当前商品的所有属性值
    sku_object_attr_values = sku_object.sale_attr_value.all()

    sku_sale_attr_val = [sku_object_attr_value.name for sku_object_attr_value in sku_object_attr_values]
    sku_sale_attr_name = [sku_object_attr_value.spu_sale_attr.name for sku_object_attr_value in
                          sku_object_attr_values]
    sku_object_dict = {
        'id': sku_object.id,
        'name': sku_object.name,
        'price': sku_object.price,
        'default_image_url': sku_object.default_image_url.name,
        'count': number,
        'selected': status,
        'sku_sale_attr_name': sku_sale_attr_name,
        'sku_sale_attr_val': sku_sale_attr_val
    }
    return sku_object_dict

def build_data(id_list, username, is_all=True):
    conn = get_redis_connection(alias='carts')
    data = []
    cache_key = f'carts_{username}'
    sku_objects = SKU.objects.filter(id__in=id_list)
    for sku_object in sku_objects:
        # 获取缓存中当前商品的购买数量和状态
        cache_value_dict = json.loads(conn.hget(cache_key, sku_object.id))

        # *************************************************************
        sku_object_dict = build_single_data(sku_object, cache_value_dict['count'], cache_value_dict['status'])
        # *************************************************************
        if is_all:
            data.append(sku_object_dict)
        else:
            if cache_value_dict['status']:
                data.append(sku_object_dict)
    return data
def advance(request, username):
    settlement_type = request.GET.get('settlement_type')
    user_profile = UserProfile.objects.get(username=username)
    addresses = list(
        Address.objects.filter(user_profile=user_profile, is_delete=False).values('id', 'address', name=F('receiver'),
                                                                                  mobile=F('receiver_mobile'),
                                                                                  title=F('tag')))
    # 商品详情中的立即购买
    if settlement_type == '1':
        sku_id = request.GET.get('sku_id')
        buy_num = request.GET.get('buy_num')
        sku_object = SKU.objects.get(id=sku_id)
        sku_object_dict = build_single_data(sku_object, buy_num, True)
        context = {
            'code': 200,
            'base_url': settings.DADASHOP_MEDIA,
            'data': {
                'addresses': addresses,
                'sku_list': [sku_object_dict],
                'sku_id': sku_id,
                'buy_count': buy_num
            }
        }
    # 购物车中的去结算
    if settlement_type == '0':
        cache_key = f'carts_{username}'
        id_list = get_redis_connection(alias='carts').hkeys(cache_key)
        sku_list = build_data(id_list, username, False)
        context = {
            'code': 200,
            'base_url': settings.DADASHOP_MEDIA,
            'data': {
                'addresses': addresses,
                'sku_list': sku_list
            }
        }

    return JsonResponse(context)


class OrdersView(View):
    def __init__(self):
        self.conn = get_redis_connection(alias='carts')

    def post(self, request, username):
        data = json.loads(request.body)
        address_id = data.get('address_id')
        try:
            user = UserProfile.objects.get(username=username)
        except Exception as e:
            return JsonResponse({'code': 400, 'errmsg': e})
        try:
            address = Address.objects.get(id=address_id)
        except Exception as e:
            return JsonResponse({'code': 400, 'errmsg': '地址不存在'})
        settlement_type = data.get('settlement_type')
        order_id = datetime.now().strftime('%Y%m%d%H%M%S%f') + str(random.randint(100000, 999999))
        if settlement_type == '1':
            buy_count = int(data.get('buy_count', 1))
            sku_id = data.get('sku_id')
            sku = SKU.objects.get(id=sku_id)
            price = float(sku.price) * buy_count
            orderinfo = OrderInfo.objects.create(
                user_profile=user,
                order_id=order_id,
                total_amount=price,
                total_count=buy_count,
                pay_method=1,
                freight=0,
                status=1,
                receiver=address.receiver,
                address=address.address,
                receiver_mobile=address.receiver_mobile,
                tag=address.tag,
            )
            OrderGoods.objects.create(
                order_info=orderinfo,
                sku=sku,
                count=buy_count,
                price=sku.price,
            )
        elif settlement_type == '0':
            list1 = data.get('sku_list') or []
            if list1:
                sku_ids = [item.get('id') or item.get('sku_id') for item in list1 if item.get('id') or item.get('sku_id')]
            else:
                cache_key = f'carts_{username}'
                raw_keys = self.conn.hkeys(cache_key)
                sku_ids = [int(k.decode()) if isinstance(k, bytes) else int(k) for k in raw_keys]
            price, buy_count = 0, 0
            for sid in sku_ids:
                sku = SKU.objects.get(id=sid)
                raw_val = self.conn.hget(f'carts_{username}', sid if isinstance(sid, (str, bytes)) else str(sid))
                value = json.loads(raw_val) if raw_val else {'count': 1}
                count = int(value.get('count', 1))
                buy_count += count
                price += count * float(sku.price)
            orderinfo = OrderInfo.objects.create(
                user_profile=user,
                order_id=order_id,
                total_amount=price,
                total_count=buy_count,
                pay_method=1,
                freight=0,
                status=1,
                receiver=address.receiver,
                address=address.address,
                receiver_mobile=address.receiver_mobile,
                tag=address.tag,
            )
            for sid in sku_ids:
                sku = SKU.objects.get(id=sid)
                raw_val = self.conn.hget(f'carts_{username}', sid if isinstance(sid, (str, bytes)) else str(sid))
                val = json.loads(raw_val) if raw_val else {'count': 1}
                OrderGoods.objects.create(
                    order_info=orderinfo,
                    sku=sku,
                    count=val.get('count', 1),
                    price=sku.price,
                )
            for sid in sku_ids:
                self.conn.hdel(f'carts_{username}', sid if isinstance(sid, (str, bytes)) else str(sid))
        app_private_key_string = settings.ALIPAY_APP_PRIVATE_KEY
        with open(settings.BASE_DIR / 'app_key/alipay_public_key.pem') as a:
            alipay_public_key_string = a.read()
        alipay_object = AliPay(
            appid=settings.ALIPAY_APP_ID,
            app_notify_url=settings.ALIPAY_APP_NOTIFY_URL,
            app_private_key_string=app_private_key_string,
            alipay_public_key_string=alipay_public_key_string,
        )
        alipay_pay_url_params = alipay_object.api_alipay_trade_page_pay(
            subject=f'{username}_茗越山关跨境电商 9710 报关数字系统_确认支付',
            out_trade_no=order_id,
            total_amount=float(price),
            return_url='http://127.0.0.1:8000/v1/pays/notify',
        )
        data = {
            'saller': settings.ALIPAY_SALLER_NAME,
            'total_amount': price,
            'order_id': order_id,
            'pay_url': settings.ALIPAY_PAY_URL + alipay_pay_url_params,
            'carts_count': buy_count
        }
        context = {
            'code': 200,
            'data': data,
        }

        return JsonResponse(context)

    def get(self, request, username):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header:
            return JsonResponse({'code': 401, 'error': '请先登录'}, status=401)
        try:
            token = auth_header.split(' ')[-1] if ' ' in auth_header else auth_header
            payload = jwt_decode(token)
            user = UserProfile.objects.get(id=payload.get('id'))
        except Exception:
            return JsonResponse({'code': 401, 'error': '登录已过期，请重新登录'}, status=401)
        if user.username != username:
            return JsonResponse({'code': 403, 'error': '无权查看此订单'}, status=403)
        type = request.GET.get('type') or '0'
        if type == '0':
            # 全部订单
            orderinfo = OrderInfo.objects.filter(user_profile=user)
        elif type == '1':
            # 待付款
            orderinfo = OrderInfo.objects.filter(user_profile=user, status=1)
        elif type == '2':
            # 代发货
            orderinfo = OrderInfo.objects.filter(user_profile=user, status=2)
        elif type == '3':
            # 待收货
            orderinfo = OrderInfo.objects.filter(user_profile=user, status=3)
        elif type == '4':
            # 已完成
            orderinfo = OrderInfo.objects.filter(user_profile=user, status=4)
        elif type == '5':
            order_id = request.GET.get('order_id')
            try:
                oderinfo = OrderInfo.objects.get(order_id=order_id, user_profile=user)
            except OrderInfo.DoesNotExist:
                return JsonResponse({'code': 404, 'error': '订单不存在'}, status=404)
            carts_count = oderinfo.total_count
            total_amount = oderinfo.total_amount
            app_private_key_string = settings.ALIPAY_APP_PRIVATE_KEY
            with open(settings.BASE_DIR / 'app_key/alipay_public_key.pem') as a:
                alipay_public_key_string = a.read()
            alipay_object = AliPay(
                appid=settings.ALIPAY_APP_ID,
                app_notify_url=settings.ALIPAY_APP_NOTIFY_URL,
                app_private_key_string=app_private_key_string,
                alipay_public_key_string=alipay_public_key_string
            )
            alipay_pay_url_params = alipay_object.api_alipay_trade_page_pay(
                subject=f'{username}_茗越山关跨境电商 9710 报关数字系统_确认支付',
                out_trade_no=order_id,
                total_amount=float(total_amount),
                return_url='http://127.0.0.1:8000/v1/pays/notify'
            )
            context = {
                'code': 200,
                'data': {
                    'order_id': order_id,
                    'carts_count': carts_count,
                    'total_amount': total_amount,
                    'saller': settings.ALIPAY_SALLER_NAME,
                    'pay_url': settings.ALIPAY_PAY_URL + alipay_pay_url_params
                }
            }
            return JsonResponse(context)
        orders_list = orderinfo.values(
            'order_id',
            'status',
            'receiver',
            'tag',
            'address',
            'receiver_mobile',
            'created_time',
            order_total_count=F('total_count'),
            order_total_amount=F('total_amount'),
            order_freight=F('freight'),
        )
        for dict1 in orders_list:
            title = dict1.get('tag')
            address = dict1.get('address')
            mobile = dict1.get('receiver_mobile')
            receiver = dict1.get('receiver')
            order_time = dict1.get('created_time')
            order_time = order_time.strftime('%Y-%m-%d %H:%M:%S')
            dict1.update({
                "address": {
                    "title": title,
                    "address": address,
                    "mobile": mobile,
                    "receiver": receiver
                },
                'order_time': order_time,
            })
        for order in orderinfo:
            order_good = list(OrderGoods.objects.filter(order_info=order).values(
                'id',
                'count',
                'price',
                'sku',
                name=F('sku__name'),
                default_image_url=F('sku__default_image_url'),
                total_amount=F('count') * F('price'),
            ))
            for dict1 in order_good:
                sku = SKU.objects.get(id=dict1.get('sku'))
                # 确保空图片路径不导致前端请求 /media/
                if not dict1.get('default_image_url'):
                    dict1['default_image_url'] = None
                dict1.update({
                    "sku_sale_attr_names": [item.name for item in sku.spu.spusaleattr_set.all()],
                    "sku_sale_attr_vals": [item.name for item in sku.sale_attr_value.all()],
                })
            for dict1 in orders_list:
                if order.order_id == dict1.get('order_id'):
                    dict1.update({
                        'order_sku': order_good,
                    })

        data = {'orders_list': list(orders_list)}
        context = {"code": 200, "data": data, "base_url": settings.DADASHOP_MEDIA}
        return JsonResponse(context)

    def put(self, request, username):
        """顾客确认收货：状态 3→4，扣减商家库存"""
        logger.info('PUT confirm_receipt: username=%s, path=%s', username, request.path)
        auth_header = request.headers.get('Authorization', '')
        if not auth_header:
            return JsonResponse({'code': 401, 'error': '未提供认证令牌'}, status=401)
        try:
            token = auth_header.split(' ')[-1] if ' ' in auth_header else auth_header
            payload = jwt_decode(token)
            user = UserProfile.objects.get(id=payload.get('id'))
        except Exception as e:
            return JsonResponse({'code': 401, 'error': f'认证失败: {str(e)}'}, status=401)
        if user.username != username:
            return JsonResponse({'code': 403, 'error': '无权操作'}, status=403)
        
        try:
            data = json.loads(request.body)
            order_id = data.get('order_id')
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning('PUT confirm_receipt parse error: %s, body=%s', e, request.body[:200] if request.body else b'')
            return JsonResponse({'code': 400, 'error': '请求参数错误'}, status=400)
        if not order_id:
            return JsonResponse({'code': 400, 'error': '缺少订单号'}, status=400)
        logger.info('PUT confirm_receipt: order_id=%s, user_id=%s', order_id, user.id)
        try:
            order = OrderInfo.objects.get(order_id=order_id, user_profile=user)
        except OrderInfo.DoesNotExist:
            logger.warning('PUT confirm_receipt: order not found order_id=%s user=%s', order_id, user.username)
            return JsonResponse({'code': 404, 'error': '订单不存在'}, status=404)
        
        if order.status != 3:
            return JsonResponse({'code': 400, 'error': '当前状态不可确认收货'}, status=400)
        
        with transaction.atomic():
            order.status = 4
            order.save(update_fields=['status', 'updated_time'])
            # 库存已在商家发货时扣减，此处不再重复扣减

        return JsonResponse({'code': 200, 'msg': '确认收货成功'})


def confirm_receipt(request, username):
    """确认收货（POST 接口，兼容性更好）"""
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'error': '请使用 POST 方法'}, status=405)
    auth_header = request.headers.get('Authorization', '')
    if not auth_header:
        return JsonResponse({'code': 401, 'error': '未提供认证令牌'}, status=401)
    try:
        token = auth_header.split(' ')[-1] if ' ' in auth_header else auth_header
        payload = jwt_decode(token)
        user = UserProfile.objects.get(id=payload.get('id'))
    except Exception as e:
        return JsonResponse({'code': 401, 'error': f'认证失败: {str(e)}'}, status=401)
    if user.username != username:
        return JsonResponse({'code': 403, 'error': '无权操作'}, status=403)
    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'code': 400, 'error': '请求参数错误'}, status=400)
    if not order_id:
        return JsonResponse({'code': 400, 'error': '缺少订单号'}, status=400)
    try:
        order = OrderInfo.objects.get(order_id=order_id, user_profile=user)
    except OrderInfo.DoesNotExist:
        return JsonResponse({'code': 404, 'error': '订单不存在'}, status=404)
    if order.status != 3:
        return JsonResponse({'code': 400, 'error': '当前状态不可确认收货'}, status=400)
    with transaction.atomic():
        order.status = 4
        order.save(update_fields=['status', 'updated_time'])
    return JsonResponse({'code': 200, 'msg': '确认收货成功'})


def delete_order(request, username):
    """删除订单（仅支持待付款状态）"""
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'error': '请使用 POST 方法'}, status=405)
    auth_header = request.headers.get('Authorization', '')
    if not auth_header:
        return JsonResponse({'code': 401, 'error': '未提供认证令牌'}, status=401)
    try:
        token = auth_header.split(' ')[-1] if ' ' in auth_header else auth_header
        payload = jwt_decode(token)
        user = UserProfile.objects.get(id=payload.get('id'))
    except Exception as e:
        return JsonResponse({'code': 401, 'error': f'认证失败: {str(e)}'}, status=401)
    if user.username != username:
        return JsonResponse({'code': 403, 'error': '无权操作'}, status=403)
    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'code': 400, 'error': '请求参数错误'}, status=400)
    if not order_id:
        return JsonResponse({'code': 400, 'error': '缺少订单号'}, status=400)
    try:
        order = OrderInfo.objects.get(order_id=order_id, user_profile=user)
    except OrderInfo.DoesNotExist:
        return JsonResponse({'code': 404, 'error': '订单不存在'}, status=404)
    if order.status not in (1, 4):
        return JsonResponse({'code': 400, 'error': '仅待付款或已完成订单可删除'}, status=400)
    try:
        with transaction.atomic():
            order.delete()
    except Exception as e:
        logger.exception('delete_order failed: order_id=%s, error=%s', order_id, e)
        return JsonResponse({'code': 500, 'error': f'删除失败: {str(e)}'}, status=500)
    return JsonResponse({'code': 200, 'msg': '订单已删除'})
