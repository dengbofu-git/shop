import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.db import IntegrityError, OperationalError
from orders.reservations import ReservationError
from .service import accept_notification, checkout_payment_data


@never_cache
def checkout_payment(request):
    from orders.checkout_views import error_response
    from users.access import account_access
    from users.decorators import get_user_from_request
    if request.method != 'POST':
        return error_response(ReservationError('METHOD_NOT_ALLOWED', '请使用POST', 405))
    try:
        user, error = get_user_from_request(request)
        if error is not None or not user.is_active:
            raise ReservationError('UNAUTHENTICATED', '请先登录有效账号', 401)
        if account_access(user)['redirect_url'] != '/buyer_dashboard.html':
            raise ReservationError('FORBIDDEN', '仅本人买家可以付款', 403)
        if len(request.body) > 20000:
            raise ReservationError('INVALID_JSON', '请求格式错误', 400)
        payload = json.loads(request.body)
        if not isinstance(payload, dict):
            raise ReservationError('INVALID_JSON', '请求格式错误', 400)
        data = checkout_payment_data(user, payload.get('checkout_id'))
        return JsonResponse({'code': 200, 'data': data})
    except ReservationError as exc:
        return error_response(exc)
    except (ValueError, TypeError, UnicodeDecodeError):
        return error_response(ReservationError('INVALID_REQUEST', '请求参数无效', 400))
    except OperationalError:
        return error_response(ReservationError('PAYMENT_BUSY', '支付状态正在更新，请稍后重试', 503))


@csrf_exempt
@never_cache
def notify(request):
    """Only a verified asynchronous provider POST may confirm payment."""
    if request.method == 'GET':
        return redirect('/myOrder.html?payment=checking')
    if request.method != 'POST':return HttpResponse('failure',status=405)
    if len(request.body)>20000 or any(len(values)!=1 for _,values in request.POST.lists()):
        return HttpResponse('failure',status=400)
    try:
        accept_notification(request.POST.dict())
        return HttpResponse('success')
    except ReservationError as exc:return HttpResponse('failure',status=exc.status)
    except (IntegrityError,ValueError,TypeError):return HttpResponse('failure',status=400)
    except OperationalError:return HttpResponse('failure',status=503)
