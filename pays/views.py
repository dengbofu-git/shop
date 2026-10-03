from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render, redirect
from orders.models import OrderInfo

def notify(request):
    """支付成功回调：更新订单状态并跳转到我的订单页"""
    out_trade_no = request.GET.get('out_trade_no')
    if out_trade_no:
        OrderInfo.objects.filter(order_id=out_trade_no).update(status=2)
    # 使用当前请求的 origin 确保跳转到正确的页面（与用户访问的域名/端口一致）
    base_url = request.build_absolute_uri('/').rstrip('/')
    return redirect(base_url + '/myOrder.html')
