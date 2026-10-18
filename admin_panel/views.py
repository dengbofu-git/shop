from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.db.models import Q
from dadashop.utils import md5
from users.decorators import platform_permission_required
from users.models import UserProfile
import json
import logging

from django.views.decorators.http import require_GET

from .analytics import build_platform_overview


@require_GET
@platform_permission_required('data_view')
def platform_overview(request):
    try:
        response = JsonResponse({'code': 200, 'data': build_platform_overview()})
    except Exception:
        logging.getLogger(__name__).exception('Platform overview unavailable')
        response = JsonResponse({'code': 503, 'error': '交易数据暂时不可用，请稍后重试'}, status=503)
    response['Cache-Control'] = 'no-store'
    return response


def _serialize_admin_user(user):
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email or '',
        'phone': user.phone or '',
        'user_type': user.user_type,
        'user_type_label': '茶企商家' if user.is_merchant() else '买家用户',
        'shop_name': user.shop_name or '',
        'is_active': user.is_active,
        'created_time': user.created_time.strftime('%Y-%m-%d %H:%M') if user.created_time else '',
    }


@method_decorator(platform_permission_required('user_manage'), name='dispatch')
class UserManagementView(View):
    """平台运营 - 买家 / 商家账号增删改查"""

    def get(self, request):
        try:
            user_type = (request.GET.get('user_type') or '').strip()
            keyword = (request.GET.get('keyword') or '').strip()
            qs = UserProfile.objects.all().order_by('-id')
            if user_type in ('customer', 'merchant'):
                qs = qs.filter(user_type=user_type)
            if keyword:
                qs = qs.filter(
                    Q(username__icontains=keyword)
                    | Q(email__icontains=keyword)
                    | Q(phone__icontains=keyword)
                    | Q(shop_name__icontains=keyword)
                )
            data = [_serialize_admin_user(u) for u in qs[:300]]
            return JsonResponse({'code': 200, 'data': data})
        except Exception as e:
            return JsonResponse({'code': 500, 'error': str(e)})

    def post(self, request):
        try:
            data = json.loads(request.body)
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()
            email = data.get('email', '').strip()
            phone = data.get('phone', '').strip()
            user_type = data.get('user_type', 'customer')
            shop_name = (data.get('shop_name') or '').strip()

            if len(username) < 6 or len(username) > 11:
                return JsonResponse({'code': 400, 'error': '用户名长度只能为6~11位之间'})
            if len(password) < 6 or len(password) > 12:
                return JsonResponse({'code': 400, 'error': '密码长度只能为6~12位之间'})
            if user_type not in ('customer', 'merchant'):
                return JsonResponse({'code': 400, 'error': '账号类型无效'})
            if user_type == 'merchant' and not shop_name:
                return JsonResponse({'code': 400, 'error': '茶企商家须填写店铺名称'})

            if UserProfile.objects.filter(username=username).exists():
                return JsonResponse({'code': 400, 'error': f'用户名{username}已经被占用'})
            if email and UserProfile.objects.filter(email=email).exists():
                return JsonResponse({'code': 400, 'error': '邮箱已经被占用'})
            if phone and UserProfile.objects.filter(phone=phone).exists():
                return JsonResponse({'code': 400, 'error': '手机号码已经被占用'})

            user = UserProfile.objects.create(
                username=username,
                password=md5(password),
                email=email or f'{username}@dadashop.com',
                phone=phone or '',
                user_type=user_type,
                shop_name=shop_name if user_type == 'merchant' else None,
                is_active=True,
            )

            return JsonResponse({'code': 200, 'data': _serialize_admin_user(user)})
        except Exception as e:
            return JsonResponse({'code': 500, 'error': str(e)})

    def put(self, request):
        try:
            data = json.loads(request.body)
            uid = data.get('id')
            if not uid:
                return JsonResponse({'code': 400, 'error': '缺少用户 id'})
            try:
                user = UserProfile.objects.get(pk=uid)
            except UserProfile.DoesNotExist:
                return JsonResponse({'code': 404, 'error': '用户不存在'})

            email = (data.get('email') or user.email or '').strip()
            phone = (data.get('phone') or user.phone or '').strip()
            user_type = data.get('user_type', user.user_type)
            shop_name = (data.get('shop_name') or '').strip()
            is_active = data.get('is_active', user.is_active)
            password = (data.get('password') or '').strip()

            if user_type not in ('customer', 'merchant'):
                return JsonResponse({'code': 400, 'error': '账号类型无效'})
            if user_type == 'merchant' and not shop_name and not user.shop_name:
                return JsonResponse({'code': 400, 'error': '茶企商家须填写店铺名称'})
            if email and UserProfile.objects.filter(email=email).exclude(pk=user.pk).exists():
                return JsonResponse({'code': 400, 'error': '邮箱已被占用'})
            if phone and UserProfile.objects.filter(phone=phone).exclude(pk=user.pk).exists():
                return JsonResponse({'code': 400, 'error': '手机号已被占用'})
            if password and (len(password) < 6 or len(password) > 12):
                return JsonResponse({'code': 400, 'error': '新密码长度须为 6~12 位'})

            user.email = email or user.email
            user.phone = phone or user.phone
            user.user_type = user_type
            user.is_active = bool(is_active)
            if user_type == 'merchant':
                user.shop_name = shop_name or user.shop_name
            else:
                user.shop_name = None
            if password:
                user.password = md5(password)
            user.save()

            return JsonResponse({'code': 200, 'data': _serialize_admin_user(user)})
        except Exception as e:
            return JsonResponse({'code': 500, 'error': str(e)})

    def delete(self, request):
        try:
            uid = request.GET.get('id')
            if not uid:
                return JsonResponse({'code': 400, 'error': '缺少用户 id'})
            operator = getattr(request, 'user_profile', None)
            if operator and str(operator.id) == str(uid):
                return JsonResponse({'code': 400, 'error': '不能删除当前登录账号'})
            deleted, _ = UserProfile.objects.filter(pk=uid).delete()
            if not deleted:
                return JsonResponse({'code': 404, 'error': '用户不存在'})
            return JsonResponse({'code': 200})
        except Exception as e:
            return JsonResponse({'code': 500, 'error': str(e)})
