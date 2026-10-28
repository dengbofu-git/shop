from django.http import HttpResponse, JsonResponse
import json
from django.conf import settings
from goods.models import SKU
from goods.images import sku_image_name
from users.models import UserProfile
from django.views import View
from django_redis import get_redis_connection


def get_available_stock(sku):
    from inventory.availability import available_quantity
    return available_quantity(sku)


class CartsView(View):
    def __init__(self):
        self.conn = get_redis_connection(alias='carts')

    def dispatch(self,request,username,*args,**kwargs):
        from users.decorators import get_user_from_request
        from users.access import account_access
        user,error=get_user_from_request(request)
        if error is not None:return error
        if not user.is_active:return JsonResponse({'code':401,'error':'账号已停用'},status=401)
        if user.username!=username or account_access(user)['redirect_url']!='/buyer_dashboard.html':
            return JsonResponse({'code':403,'error':'只能操作本人的采购车'},status=403)
        if request.method in ('POST','PUT','DELETE'):
            try:
                if not isinstance(json.loads(request.body),dict):raise ValueError()
            except (ValueError,UnicodeDecodeError):return JsonResponse({'code':400,'error':'请求格式无效'},status=400)
        request.cart_user = user
        return super().dispatch(request,username,*args,**kwargs)


    def post(self, request, username):
        data = json.loads(request.body)
        sku_id = data.get('sku_id')
        count=data.get('count')
        if isinstance(count,bool) or not 1<=len(str(count))<=9 or not str(count).isascii() or not str(count).isdigit() or int(count)<1:
            return JsonResponse({'code':400,'error':'数量必须为正整数'},status=400)
        count=int(count)
        if isinstance(sku_id, bool) or not str(sku_id).isascii() or not str(sku_id).isdigit() or not 1 <= len(str(sku_id)) <= 9 or int(sku_id) < 1:
            return JsonResponse({'code':400,'error':'商品标识无效'},status=400)
        sku_id=int(sku_id)
        from goods.availability import sellable_skus
        from .atomic_add import add_items, CartError, request_hash, previous_receipt
        import uuid
        fingerprint = request_hash({'sku_id':str(sku_id),'count':count})
        try:
            operation = str(uuid.UUID(request.headers.get('Idempotency-Key'))) if request.headers.get('Idempotency-Key') else str(uuid.uuid4())
            old = previous_receipt(self.conn, username, operation, fingerprint)
            if old is not None:
                return JsonResponse(old)
            sku = sellable_skus().filter(pk=sku_id).first()
            if sku is None:
                return JsonResponse({'code':30101,'error':'商品已下架或暂不可售'})
            return JsonResponse(add_items(self.conn, username, operation, fingerprint, [
                {'sku_id':str(sku.pk),'count':count,'available_stock':sku.sellable_stock}]))
        except CartError as error:
            return JsonResponse({'code':30103,'error':str(error)})
        except (ValueError, TypeError) as error:
            return JsonResponse({'code':400,'error':str(error) if isinstance(error, CartError) else '商品或操作标识无效'},
                                status=error.status if isinstance(error, CartError) else 400)
        except Exception:
            return JsonResponse({'code':503,'error':'采购车服务暂不可用'},status=503)


    def get(self, request, username):
        try:
            user = UserProfile.objects.get(username=username)
        except Exception as e:
            context = {
                'code': 30104,
                'error': '未找到用户',
            }
            return JsonResponse(context)
        cache_key = f'carts_{username}'
        if not self.conn.exists(cache_key):
            context = {
                'code': 200,
                'data': [],
                'base_url': settings.TEA_SAAS_MEDIA
            }
            return JsonResponse(context)
        info = self.conn.hgetall(name=cache_key)
        skus_list = []
        for key, value in info.items():
            sku_id = int(key) if isinstance(key, (int, str)) else int(key.decode('utf-8'))
            try:
                sku = SKU.objects.get(id=sku_id)
            except SKU.DoesNotExist:
                continue
            value = json.loads(value)
            available_stock = get_available_stock(sku)
            count = int(value.get('count', 1))
            if count > available_stock:
                count = max(0, available_stock)
                value['count'] = str(count)
                self.conn.hset(name=cache_key, key=key, value=json.dumps(value))
            if count <= 0:
                self.conn.hdel(cache_key, key)
                continue
            unit_price = float(sku.price)
            skus_list.append({
                "id": str(sku_id),
                "name": sku.name,
                "count": count,
                "available_stock": available_stock,
                "selected": value.get('status'),
                "default_image_url": sku_image_name(sku),
                "unit_price": unit_price,
                "price": unit_price * count,
                "sku_sale_attr_name": [item.name for item in sku.spu.spusaleattr_set.all()],
                "sku_sale_attr_val": [item.name for item in sku.sale_attr_value.all()],
            })
        context = {
            'code': 200,
            'data': skus_list,
            'base_url': settings.TEA_SAAS_MEDIA
        }
        return JsonResponse(context)

    def delete(self, request, username):
        data = json.loads(request.body)
        sku_id = data.get('sku_id')
        value = json.loads(self.conn.hget(name=f'carts_{username}', key=sku_id))
        if not value:
            context = {
                'code': 30101,
                'error': '未找到商品'
            }
            return JsonResponse(context)
        count = value.get('count')
        try:
            user = UserProfile.objects.get(username=username)
        except Exception as e:
            context = {
                'code': 30104,
                'error': '未找到用户',
            }
            return JsonResponse(context)
        self.conn.hdel(f'carts_{username}', sku_id)
        carts_count = self.conn.hlen(name=f'carts_{username}')
        context = {
            'code': 200,
            'data': {
                'carts_count': carts_count,
            },
            'base_url': settings.TEA_SAAS_MEDIA
        }
        return JsonResponse(context)

    def put(self, request, username):
        data = json.loads(request.body)
        sku_id = data.get('sku_id')
        state = data.get('state')
        try:
            user = UserProfile.objects.get(username=username)
        except Exception as e:
            context = {
                'code': 30104,
                'error': '未找到用户',
            }
            return JsonResponse(context)
        if state != 'selectall' and state != 'unselectall':
            original = self.conn.hget(name=f'carts_{username}', key=sku_id)
            value = json.loads(original)
            try:
                sku = SKU.objects.get(id=sku_id)
            except Exception as e:
                context = {
                    'code': 30101,
                    'error': '未找到商品'
                }
                return JsonResponse(context)
            if state == 'add':
                value['count'] = str(int(value.get('count')) + 1)
                available_stock = get_available_stock(sku)
                if int(value.get('count')) > available_stock:
                    context = {
                        'code': 30103,
                        'error': '购买数量超过库存'
                    }
                    return JsonResponse(context)
            elif state == 'del':
                if int(value.get('count'))-1 >= 1:
                    value['count'] = str(int(value.get('count')) - 1)
            elif state == 'select':
                value['status'] = True
            elif state == 'unselect':
                value['status'] = False
            unit_price = float(sku.price)
            count = int(value.get('count', 1))
            skus_list = [{
                "id": sku_id,
                "name": sku.name,
                "count": count,
                "selected": value.get('status'),
                "default_image_url": sku_image_name(sku),
                "unit_price": unit_price,
                "price": unit_price * count,
                "sku_sale_attr_name": [item.name for item in sku.spu.spusaleattr_set.all()],
                "sku_sale_attr_val": [item.name for item in sku.sale_attr_value.all()],
            }]
            from .atomic_add import compare_set
            if not compare_set(self.conn, f'carts_{username}', sku_id, original, json.dumps(value)):
                return JsonResponse({'code':409,'error':'采购车已发生变化，请刷新后重试'})
        else:
            values = self.conn.hgetall(name=f'carts_{username}')
            if state == 'selectall':
                for key,value in values.items():
                    original = value
                    value = json.loads(value)
                    value['status'] = True
                    from .atomic_add import compare_set
                    compare_set(self.conn, f'carts_{username}', key, original, json.dumps(value))
            elif state == 'unselectall':
                for key,value in values.items():
                    original = value
                    value = json.loads(value)
                    value['status'] = False
                    from .atomic_add import compare_set
                    compare_set(self.conn, f'carts_{username}', key, original, json.dumps(value))
            skus_list = []
            for key,value in values.items():
                sku = SKU.objects.get(id=int(key))
                value = json.loads(value)
                unit_price = float(sku.price)
                count = int(value.get('count', 1))
                skus_list.append(
                    {
                        "id": key,
                        "name": sku.name,
                        "count": count,
                        "selected": value.get('status'),
                        "default_image_url": sku_image_name(sku),
                        "unit_price": unit_price,
                        "price": unit_price * count,
                        "sku_sale_attr_name": [item.name for item in sku.spu.spusaleattr_set.all()],
                        "sku_sale_attr_val": [item.name for item in sku.sale_attr_value.all()],
                    })
        context = {
            'code': 200,
            'data': skus_list,
            'base_url': settings.TEA_SAAS_MEDIA
        }
        return JsonResponse(context)

# Create your views here.
