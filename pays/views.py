from django.http import HttpResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.db import IntegrityError, OperationalError
from orders.reservations import ReservationError
from .service import accept_notification


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
