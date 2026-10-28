import os
import re
from decimal import Decimal,InvalidOperation
from alipay import AliPay
from django.conf import settings
from django.utils import timezone
from orders.models import OrderInfo
from orders.reservations import ReservationError,confirm_payment,expire_orders


def client():
    try:
        with open(settings.BASE_DIR/'app_key/alipay_public_key.pem') as file:public_key=file.read()
        return AliPay(appid=settings.ALIPAY_APP_ID,app_notify_url=settings.ALIPAY_APP_NOTIFY_URL,
            app_private_key_string=settings.ALIPAY_APP_PRIVATE_KEY,alipay_public_key_string=public_key)
    except Exception:raise ReservationError('PAYMENT_NOT_CONFIGURED','支付服务未配置，请稍后重试',503)


def payment_data(order):
    expire_orders(user_id=order.user_profile_id)
    order.refresh_from_db()
    if not order.reservation_managed:raise ReservationError('LEGACY_ORDER_REQUIRES_REVIEW','历史订单尚未核验库存，请联系商家处理',409)
    if order.status!=1 or order.paid_at or order.expires_at<=timezone.now():raise ReservationError('ORDER_NOT_PAYABLE','订单已关闭或不再需要付款，请刷新订单列表',409)
    if not getattr(settings,'ALIPAY_SELLER_ID',os.getenv('ALIPAY_SELLER_ID','')):
        raise ReservationError('PAYMENT_NOT_CONFIGURED','支付服务尚未完成收款方校验配置，请联系平台',503)
    url=client().api_alipay_trade_page_pay(subject='tea_saas采购订单',out_trade_no=order.pk,total_amount=str(order.total_amount),
        return_url=getattr(settings,'PAYMENT_RETURN_URL','http://127.0.0.1:8000/v1/pays/notify'),time_expire=timezone.localtime(order.expires_at).strftime('%Y-%m-%d %H:%M:%S'))
    return {'order_id':order.pk,'carts_count':order.total_count,'total_amount':str(order.total_amount),
            'saller':settings.ALIPAY_SALLER_NAME,'pay_url':settings.ALIPAY_PAY_URL+url,'expires_at':order.expires_at.isoformat()}


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
    return confirm_payment(payload.get('out_trade_no'),payload['trade_no'],amount)
