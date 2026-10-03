"""
物流调度服务
"""
from .models import LogisticsProvider, ShippingOrder, ShippingTrack
from orders.models import OrderInfo


class LogisticsService:
    """物流服务类"""
    
    @staticmethod
    def select_provider(order_info, weight=0):
        """智能选择物流供应商"""
        # 根据订单地址、重量、时效选择最优物流
        providers = LogisticsProvider.objects.filter(is_active=True)
        
        # 简单策略：选择第一个启用的供应商
        # 实际应用中可以根据地址、重量、时效等条件选择
        return providers.first()
    
    @staticmethod
    def create_shipping_order(order_info, provider=None, tracking_number=None):
        """创建物流订单"""
        if not provider:
            provider = LogisticsService.select_provider(order_info)
        
        shipping_order = ShippingOrder.objects.create(
            order_info=order_info,
            provider=provider,
            tracking_number=tracking_number or f"SF{order_info.order_id}",
            receiver_name=order_info.receiver,
            receiver_phone=order_info.receiver_mobile,
            receiver_address=order_info.address,
        )
        
        # 创建初始追踪记录
        ShippingTrack.objects.create(
            shipping_order=shipping_order,
            status=1,
            status_text='物流订单已创建',
        )
        
        return shipping_order
    
    @staticmethod
    def update_tracking(shipping_order, status, status_text, location=None, remark=None):
        """更新物流追踪"""
        shipping_order.status = status
        shipping_order.save()
        
        ShippingTrack.objects.create(
            shipping_order=shipping_order,
            status=status,
            status_text=status_text,
            location=location,
            remark=remark,
        )
        
        return shipping_order
