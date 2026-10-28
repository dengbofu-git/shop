"""Merchant HTTP facade: bounded uploads, immutable previews and explicit commit."""
import csv
from functools import wraps
from io import BytesIO, StringIO
import json
import logging

from django.db import DatabaseError
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from tea_saas.utils import jwt_decode
from users.models import UserProfile
from .product_import_parser import MAX_BYTES, ImportFileError, TEMPLATE_HEADERS, TEMPLATE_ROW
from .product_import_service import ImportConflict, commit_job, create_job, get_job, job_dto

logger = logging.getLogger(__name__)


def _error(message, status):
    response = JsonResponse({'code': status, 'error': message}, status=status)
    response['Cache-Control'] = 'no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def merchant_endpoint(view):
    @wraps(view)
    def guarded(request, *args, **kwargs):
        try:
            token = request.headers.get('Authorization', '').split()
            if not token or len(token) > 2 or len(token[-1]) > 4096 or (len(token) == 2 and token[0].lower() != 'bearer'):
                return _error('请先登录商家账号', 401)
            try:
                payload = jwt_decode(token[-1])
            except Exception:
                return _error('登录已失效，请重新登录', 401)
            user = UserProfile.objects.filter(pk=payload.get('id'), is_active=True).first()
            if user is None:
                return _error('登录已失效，请重新登录', 401)
            if not (user.is_merchant() or user.has_role('supplier')):
                return _error('仅活跃商家可使用商品导入', 403)
            request.user_profile = user
            response = view(request, *args, **kwargs)
        except (ImportFileError, ImportConflict) as exc:
            response = _error(str(exc), getattr(exc, 'status', 400))
        except DatabaseError:
            response = _error('商品导入存储暂不可用，请联系管理员检查服务及迁移状态', 503)
        except Exception as exc:
            # Never echo private cells, filenames, credentials or database diagnostics.
            logger.error('product_import_failed:%s', type(exc).__name__)
            response = _error('导入失败，本批未写入；请重试或联系管理员', 500)
        response['Cache-Control'] = 'no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    return guarded


@merchant_endpoint
@require_POST
def upload(request):
    if set(request.POST) != {'request_key'} or set(request.FILES) != {'file'} or len(request.FILES.getlist('file')) != 1:
        raise ImportFileError('请选择一个文件，不接受额外参数')
    source = request.FILES['file']
    if source.size > MAX_BYTES:
        return _error('文件不得超过 5 MB', 413)
    chunks, size = [], 0
    for part in source.chunks():
        size += len(part)
        if size > MAX_BYTES:
            return _error('文件不得超过 5 MB', 413)
        chunks.append(part)
    job = create_job(request.user_profile, source.name, b''.join(chunks), request.POST['request_key'])
    return JsonResponse({'code': 200, 'data': job_dto(job)})


@merchant_endpoint
@require_GET
def detail(request, job_id):
    return JsonResponse({'code': 200, 'data': job_dto(get_job(request.user_profile, job_id))})


@merchant_endpoint
@require_POST
def commit(request, job_id):
    if len(request.body) > 1024:
        raise ImportFileError('确认请求过大')
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeError):
        raise ImportFileError('确认请求格式错误') from None
    if (not isinstance(payload, dict) or set(payload) != {'review_digest'}
            or not isinstance(payload['review_digest'], str) or len(payload['review_digest']) != 64):
        raise ImportFileError('请提交预览摘要，不接受商品或商家字段')
    return JsonResponse({'code': 200, 'data': job_dto(commit_job(
        request.user_profile, job_id, payload['review_digest']))})


@merchant_endpoint
@require_GET
def template(request):
    kind = request.GET.get('format', 'xlsx')
    if kind == 'csv':
        stream = StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerows([TEMPLATE_HEADERS, TEMPLATE_ROW])
        response = HttpResponse(b'\xef\xbb\xbf' + stream.getvalue().encode('utf-8'), content_type='text/csv; charset=utf-8')
    elif kind == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = '商品导入'
        sheet.append(TEMPLATE_HEADERS)
        sheet.append(TEMPLATE_ROW)
        sheet.freeze_panes = 'A2'
        for cell in sheet[1]:
            cell.font = Font(bold=True, color='185C3B')
            sheet.column_dimensions[cell.column_letter].width = 22
        stream = BytesIO()
        workbook.save(stream)
        workbook.close()
        response = HttpResponse(stream.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        raise ImportFileError('模板格式仅支持 xlsx 或 csv')
    response['Content-Disposition'] = 'attachment; filename="product-import-template.{}"'.format(kind)
    return response
