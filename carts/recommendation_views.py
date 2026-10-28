"""用户点击后的业务写入口，不向Agent或MCP开放。"""
from decimal import Decimal, InvalidOperation
import json
import uuid
from django.http import JsonResponse
from support_ai.models import SupportTurn
from goods.availability import sellable_skus
from .atomic_add import CartError, add_items, previous_receipt, request_hash
from .views import CartsView


def positive(value):
    return type(value) is int and 1 <= value <= 999999999


def selection(user, payload):
    try:
        identity = uuid.UUID(payload['recommendation_request_id'])
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CartError('推荐记录标识无效', 400)
    turn = SupportTurn.objects.filter(user=user, conversation__user=user, request_id=identity).first()
    if turn is None:
        raise CartError('推荐记录不存在或不属于当前账号', 404)
    response = turn.response
    bundle_id = payload.get('bundle_id')
    sku_id = payload.get('sku_id')
    if bundle_id is not None:
        if not isinstance(bundle_id, str) or not 1 <= len(bundle_id) <= 80:
            raise CartError('方案标识无效', 400)
        matches = [b for b in response.get('recommendation_bundles', []) if b.get('bundle_id') == bundle_id]
        if len(matches) != 1:
            raise CartError('该方案不在本轮推荐记录中', 404)
        cards = matches[0].get('items', [])
    else:
        cards = response.get('recommendations', [])
    if sku_id is not None:
        if not positive(sku_id) or not positive(payload.get('count', 1)):
            raise CartError('商品或购买数量无效', 400)
        cards = [c for c in cards if c.get('sku_id') == sku_id]
        if len(cards) != 1:
            raise CartError('商品不在所选推荐中', 404)
        counts = [payload.get('count', 1)]
    else:
        if bundle_id is None or 'count' in payload:
            raise CartError('整套操作必须选择方案，不能覆盖方案数量', 400)
        counts = [c.get('quantity') for c in cards]
    if not cards or len(cards) > 4 or not all(positive(n) for n in counts):
        raise CartError('推荐商品或方案数量无效，请重新推荐', 409)
    ids = [c.get('sku_id') for c in cards]
    if not all(positive(i) for i in ids) or len(set(ids)) != len(ids):
        raise CartError('推荐商品标识无效，请重新推荐')
    current = {s.pk:s for s in sellable_skus().filter(pk__in=ids)}
    items = []
    for card, count in zip(cards, counts):
        sku = current.get(card['sku_id'])
        if sku is None:
            raise CartError('推荐中的商品已下架或暂不可售，本次未添加，请重新获取推荐')
        try:
            unchanged = card.get('currency') == 'CNY' and Decimal(str(card['price'])) == sku.price
        except (InvalidOperation, KeyError, TypeError, ValueError):
            unchanged = False
        if not unchanged:
            raise CartError('商品价格或价格口径已变化，本次未添加，请重新获取推荐')
        if count > sku.sellable_stock:
            raise CartError('推荐商品的可售库存不足，本次未添加')
        items.append({'sku_id':str(sku.pk),'count':count,'available_stock':sku.sellable_stock})
    return items


class RecommendationCartView(CartsView):
    http_method_names = ['post', 'options']

    def post(self, request, username):
        payload = json.loads(request.body)
        try:
            if set(payload) - {'request_id','recommendation_request_id','bundle_id','sku_id','count'}:
                raise CartError('包含不支持的字段', 400)
            try:
                operation = str(uuid.UUID(payload['request_id']))
            except (ValueError, TypeError, KeyError, AttributeError):
                raise CartError('操作标识无效', 400)
            fingerprint = request_hash(payload)
            old = previous_receipt(self.conn, username, operation, fingerprint)
            if old is not None:
                return JsonResponse(old)
            items = selection(request.cart_user, payload)
            return JsonResponse(add_items(self.conn, username, operation, fingerprint, items))
        except CartError as error:
            return JsonResponse({'code':error.status,'error':str(error)},status=error.status)
        except Exception:
            return JsonResponse({'code':503,'error':'采购车服务暂不可用，请重试同一次操作'},status=503)
