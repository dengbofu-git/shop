from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from users.decorators import merchant_required

from .services import assistant_status


@never_cache
@require_GET
@merchant_required
def status(request):
    if not request.user_profile.is_active:
        return JsonResponse({'code': 403, 'error': '当前账号尚未激活'}, status=403)
    return JsonResponse({'code': 200, 'data': assistant_status()})
