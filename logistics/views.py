from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from users.decorators import get_user_from_request
from users.access import account_access, can_access_platform, PLATFORM_ROLES
from orders.lifecycle import merchant_ids
from django.views.decorators.cache import never_cache
from .models import ShippingOrder, ShippingTrack


@method_decorator(never_cache, name='dispatch')
class ShippingTrackView(View):
    """物流追踪"""
    
    def dispatch(self, request, *args, **kwargs):
        user, error = get_user_from_request(request)
        if error is not None:
            return error
        if not user.is_active:
            return JsonResponse({'code': 403, 'error': '账号已停用'}, status=403)
        access = account_access(user)
        platform = bool(PLATFORM_ROLES.intersection(access['roles']))
        if platform and not can_access_platform(access, 'logistics_manage'):
            return JsonResponse({'code': 403, 'error': '没有物流管理权限'}, status=403)
        request.shipping_actor = user
        request.shipping_portal = 'platform' if platform else access['redirect_url']
        if request.shipping_portal not in ('platform', '/buyer_dashboard.html', '/merchant_dashboard.html'):
            return JsonResponse({'code': 403, 'error': '无权访问物流'}, status=403)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, order_id):
        try:
            orders = ShippingOrder.objects.select_related('order_info', 'provider')
            if request.shipping_portal == '/buyer_dashboard.html':
                orders = orders.filter(order_info__user_profile=request.shipping_actor)
            shipping_order = orders.get(order_info__order_id=order_id)
            if request.shipping_portal == '/merchant_dashboard.html' and merchant_ids(shipping_order.order_info) != {request.shipping_actor.pk}:
                raise ShippingOrder.DoesNotExist
            tracks = ShippingTrack.objects.filter(shipping_order=shipping_order)
            
            track_list = []
            for track in tracks:
                track_list.append({
                    'status': track.status,
                    'status_text': track.status_text,
                    'location': track.location,
                    'remark': track.remark,
                    'time': track.created_time.strftime('%Y-%m-%d %H:%M:%S'),
                })
            
            return JsonResponse({
                'code': 200,
                'data': {
                    'tracking_number': shipping_order.tracking_number,
                    'provider': shipping_order.provider.name,
                    'status': shipping_order.status,
                    'status_text': shipping_order.get_status_display(),
                    'tracks': track_list,
                }
            })
        except ShippingOrder.DoesNotExist:
            return JsonResponse({
                'code': 10002,
                'error': '物流订单不存在'
            }, status=404)
