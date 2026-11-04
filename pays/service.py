import os
import re
from decimal import Decimal,InvalidOperation
from alipay import AliPay
from django.conf import settings
from django.utils import timezone
from orders.models import OrderInfo
from orders.reservations import ReservationError,confirm_payment,expire_orders
from .combined import prepare_checkout_payment, confirm_combined_payment


def client():
    try:
        with open(settings.BASE_DIR/'app_key/alipay_public_key.pem') as file:public_key=file.read()
        return AliPay(appid=settings.ALIPAY_APP_ID,app_notify_url=settings.ALIPAY_APP_NOTIFY_URL,
            app_private_key_string=settings.ALIPAY_APP_PRIVATE_KEY,alipay_public_key_string=public_key)
    except Exception:raise ReservationError('PAYMENT_NOT_CONFIGURED','支付服务未配置，请稍后重试',503)


def payment_data(order):
    if order.currency != 'CNY':
        raise ReservationError('CURRENCY_REVIEW_REQUIRED','原记录币种未核验，请联系平台处理付款',409)
    expire_orders(user_id=order.user_profile_id)
    order.refresh_from_db()
    if not order.reservation_managed:raise ReservationError('LEGACY_ORDER_REQUIRES_REVIEW','历史订单尚未核验库存，请联系商家处理',409)
    if order.status!=1 or order.paid_at or not order.expires_at or order.expires_at<=timezone.now():raise ReservationError('ORDER_NOT_PAYABLE','订单已关闭或不再需要付款，请刷新订单列表',409)
    if order.checkout_request_id is not None:
        return checkout_payment_data(order.user_profile, order.checkout_request_id)
    if not getattr(settings,'ALIPAY_SELLER_ID',os.getenv('ALIPAY_SELLER_ID','')):
        raise ReservationError('PAYMENT_NOT_CONFIGURED','支付服务尚未完成收款方校验配置，请联系平台',503)
    url=client().api_alipay_trade_page_pay(subject='tea_saas采购订单',out_trade_no=order.pk,total_amount=str(order.total_amount),
        return_url=getattr(settings,'PAYMENT_RETURN_URL','http://127.0.0.1:8000/v1/pays/notify'),time_expire=timezone.localtime(order.expires_at).strftime('%Y-%m-%d %H:%M:%S'))
    return {'order_id':order.pk,'carts_count':order.total_count,'total_amount':str(order.total_amount),
            'currency':order.currency,
            'saller':settings.ALIPAY_SALLER_NAME,'pay_url':settings.ALIPAY_PAY_URL+url,'expires_at':order.expires_at.isoformat()}


def checkout_payment_data(user, checkout_id):
    if not getattr(settings, 'ALIPAY_SELLER_ID', os.getenv('ALIPAY_SELLER_ID', '')):
        raise ReservationError('PAYMENT_NOT_CONFIGURED', '支付服务尚未完成收款方校验配置，请联系平台', 503)
    payment = prepare_checkout_payment(user, checkout_id)
    provider = client()
    allocations = list(payment.allocations.select_related('order').order_by('order_id'))
    payment.refresh_from_db()
    if payment.status != 'pending' or payment.payment_exception or payment.expires_at <= timezone.now():
        raise ReservationError('PAYMENT_ATTEMPT_INVALID', '原付款已失效，请刷新订单列表')
    # SDK URL construction is local signing; no channel network request is made,
    # and the database transaction has already released its lifecycle locks.
    try:
        query = provider.api_alipay_trade_page_pay(subject='tea_saas合并采购付款',
            out_trade_no=payment.pk, total_amount=str(payment.total_amount),
            return_url=getattr(settings, 'PAYMENT_RETURN_URL', 'http://127.0.0.1:8000/v1/pays/notify'),
            time_expire=timezone.localtime(payment.expires_at).strftime('%Y-%m-%d %H:%M:%S'))
    except Exception as exc:
        raise ReservationError('PAYMENT_NOT_CONFIGURED', '支付服务暂不可用，请稍后重试', 503) from exc
    rows = [{'order_id': a.order_id, 'merchant_id': a.merchant_id, 'merchant_name': a.merchant_name,
             'goods_amount': str(a.goods_amount), 'freight_amount': str(a.freight_amount),
             'total_amount': str(a.amount), 'carts_count': a.order.total_count,
             'currency': payment.currency, 'status': a.order.status,
             'expires_at': a.order.expires_at.isoformat() if a.order.expires_at else None,
             'payment_exception': a.order.payment_exception} for a in allocations]
    return {'payment_id': payment.pk, 'checkout_id': payment.checkout_id,
            'total_amount': str(payment.total_amount), 'currency': payment.currency,
            'expires_at': payment.expires_at.isoformat(), 'status': payment.status,
            'payment_exception': payment.payment_exception, 'orders': rows,
            'carts_count': sum(a.order.total_count for a in allocations),
            'saller': settings.ALIPAY_SALLER_NAME, 'pay_url': settings.ALIPAY_PAY_URL + query}


def accept_notification(data):
    payload=dict(data);signature=payload.pop('sign',None)
    seller=getattr(settings,'ALIPAY_SELLER_ID',os.getenv('ALIPAY_SELLER_ID',''))
    if not seller:raise ReservationError('PAYMENT_NOT_CONFIGURED','未配置收款方校验',503)
    if not signature or payload.get('app_id')!=settings.ALIPAY_APP_ID or payload.get('seller_id')!=seller:
        raise ReservationError('INVALID_PAYMENT_NOTIFICATION','支付通知来源不合法',400)
    try:valid=client().verify(payload,signature)
    except ReservationError:raise
    except Exception:valid=False
    if not valid:raise ReservationError('INVALID_PAYMENT_SIGNATURE','支付通知验签失败',400)
    if payload.get('trade_status') not in ('TRADE_SUCCESS','TRADE_FINISHED'):return None
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',payload.get('trade_no','')):raise ReservationError('INVALID_PAYMENT_TRADE','支付流水无效',400)
    try:
        amount=Decimal(payload.get('total_amount',''))
        if not amount.is_finite() or amount<=0 or amount!=amount.quantize(Decimal('.01')):raise ValueError()
    except (InvalidOperation,ValueError):raise ReservationError('INVALID_PAYMENT_AMOUNT','支付金额无效',400)
    target = payload.get('out_trade_no', '')
    if target.startswith('pay_'):
        return confirm_combined_payment(target, payload['trade_no'], amount)
    return confirm_payment(target,payload['trade_no'],amount)
