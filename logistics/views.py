from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from users.decorators import login_required
from .models import ShippingOrder, ShippingTrack
from .services import LogisticsService


@method_decorator(login_required, name='dispatch')
class ShippingTrackView(View):
    """物流追踪"""
    
    def get(self, request, order_id):
        try:
            shipping_order = ShippingOrder.objects.get(order_info__order_id=order_id)
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
            })
