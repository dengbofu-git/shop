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
from goods.images import sku_image_name
from users.models import UserProfile, Address
from tea_saas.utils import jwt_decode
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
        'product_name': sku_object.spu.name,
        'sku_name': sku_object.name,
        'price': sku_object.price,
        'default_image_url': sku_image_name(sku_object),
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
    from .checkout_views import buyer, error_response
    from .reservations import ReservationError
    try:user_profile = buyer(request,username)
    except ReservationError as exc:return error_response(exc)
    settlement_type = request.GET.get('settlement_type')
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
            'base_url': settings.TEA_SAAS_MEDIA,
            'data': {
                'addresses': addresses,
                'reservation_checkout_version': 1,
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
            'base_url': settings.TEA_SAAS_MEDIA,
            'data': {
                'addresses': addresses,
                'reservation_checkout_version': 1,
                'sku_list': sku_list
            }
        }

    return JsonResponse(context)


class OrdersView(View):
    def __init__(self):
        self.conn = get_redis_connection(alias='carts')

    def post(self, request, username):
        from .checkout_views import submit_order
        return submit_order(request, username, self.conn)

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
        if not user.is_active:
            return JsonResponse({'code':401,'error':'账号已停用'},status=401)
        from users.access import account_access
        if account_access(user)['redirect_url']!='/buyer_dashboard.html':
            return JsonResponse({'code':403,'error':'仅买家可访问本人订单'},status=403)
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
            from .checkout_views import error_response
            from .reservations import ReservationError
            from pays.service import payment_data
            order = OrderInfo.objects.filter(order_id=request.GET.get('order_id'), user_profile=user).first()
            if not order:return JsonResponse({'code':404,'error':'订单不存在'},status=404)
            try:return JsonResponse({'code':200,'data':payment_data(order)})
            except ReservationError as exc:return error_response(exc)
        else:
            return JsonResponse({'code':400,'error':'订单筛选参数无效'},status=400)
        from .reservations import expire_orders
        expire_orders(user_id=user.pk)
        orderinfo = orderinfo.filter(buyer_hidden=False)
        orders_list = orderinfo.values(
            'order_id',
            'status',
            'order_type',
            'reservation_managed', 'expires_at', 'closed_at', 'close_reason', 'payment_exception',
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
            from engagement.services import completed, review_state, verified_item
            order_good = list(OrderGoods.objects.filter(order_info=order).values(
                'id',
                'count',
                'price',
                'sku',
                name=F('sku__name'),
                product_name=F('sku__spu__name'),
                sku_name=F('sku__name'),
                default_image_url=F('sku__default_image_url'),
                total_amount=F('count') * F('price'),
            ))
            for dict1 in order_good:
                sku = SKU.objects.get(id=dict1.get('sku'))
                item = OrderGoods.objects.select_related('sku__spu', 'review').get(pk=dict1['id'])
                item.order_info = order
                dict1.update(review_state(item))
                dict1['can_contact'] = verified_item(item)
                # 确保空图片路径不导致前端请求 /media/
                dict1['default_image_url'] = sku_image_name(sku) or None
                dict1.update({
                    "sku_sale_attr_names": [item.name for item in sku.spu.spusaleattr_set.all()],
                    "sku_sale_attr_vals": [item.name for item in sku.sale_attr_value.all()],
                })
            for dict1 in orders_list:
                if order.order_id == dict1.get('order_id'):
                    dict1.update({
                        'order_sku': order_good,
                        'status_text': order.get_status_display_text(),
                        'is_completed': completed(order),
                        'can_cancel': order.order_type=='standard' and order.status==1 and not order.paid_at and not order.payment_exception,
                        'can_hide': (order.order_type=='standard' and order.status==0) or completed(order),
                    })

        data = {'orders_list': list(orders_list)}
        context = {"code": 200, "data": data, "base_url": settings.TEA_SAAS_MEDIA}
        return JsonResponse(context)

    def put(self, request, username):
        """顾客确认收货：状态 3→4，扣减商家库存"""
        logger.info('orders.receipt.requested')
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
            logger.warning('orders.receipt.invalid_json', extra={'error_type': type(e).__name__})
            return JsonResponse({'code': 400, 'error': '请求参数错误'}, status=400)
        if not order_id:
            return JsonResponse({'code': 400, 'error': '缺少订单号'}, status=400)
        logger.info('orders.receipt.validated')
        try:
            order = OrderInfo.objects.get(order_id=order_id, user_profile=user)
        except OrderInfo.DoesNotExist:
            logger.warning('orders.receipt.not_found')
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
    """从买家列表隐藏订单，保留交易、咨询和评价依据。"""
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
    from engagement.services import completed
    if not ((order.order_type == 'standard' and order.status == 0) or completed(order)):
        return JsonResponse({'code':409,'error':'仅已关闭或已完成订单可隐藏；待付款订单请明确取消'},status=409)
    try:
        with transaction.atomic():
            order = OrderInfo.objects.select_for_update().get(pk=order.pk, user_profile=user)
            if not ((order.order_type == 'standard' and order.status == 0) or completed(order)):
                return JsonResponse({'code': 409, 'error': '订单状态已改变，请刷新'}, status=409)
            order.buyer_hidden = True
            order.save(update_fields=['buyer_hidden', 'updated_time'])
    except Exception as e:
        logger.exception('orders.delete.failed')
        return JsonResponse({'code': 500, 'error': f'删除失败: {str(e)}'}, status=500)
    return JsonResponse({'code': 200, 'msg': '订单已从列表隐藏，交易与评价记录已保留'})
