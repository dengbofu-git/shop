"""Authenticated reads; source PDFs and images never use public static paths."""
from django.db import DatabaseError
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.views.decorators.http import require_GET
from tea_saas.utils import jwt_decode
from users.models import UserProfile
from users.access import account_access, can_access_platform
from .models import KnowledgeDocument, KnowledgePage
from .pdf_pipeline.storage import job_path


def _error(status, text):
    response = JsonResponse({'error': text}, status=status)
    response['Cache-Control'] = 'no-store'
    return response


@require_GET
def artifact(request, document_id, page_number=None):
    try:
        token = request.headers.get('Authorization', '').split()
        if len(token) != 2 or token[0].lower() != 'bearer':
            return _error(401, '请先登录')
        try:
            payload = jwt_decode(token[1])
            user = UserProfile.objects.filter(pk=payload.get('id'), is_active=True).first()
        except DatabaseError:
            raise
        except Exception:
            return _error(401, '认证已失效')
        if user is None:
            return _error(401, '认证已失效')
        documents = KnowledgeDocument.objects.select_related('pdf_import').filter(pk=document_id)
        if not can_access_platform(account_access(user), 'system_config'):
            if not user.is_customer():
                return _error(403, '没有读取权限')
            documents = documents.filter(status='published').filter(Q(visibility='public') | Q(visibility='private', owner_id=user.pk))
        document = documents.first()
        if document is None or not hasattr(document, 'pdf_import'):
            return _error(404, '资料不存在或不可访问')
        name, content_type = 'source.pdf', 'application/pdf'
        if page_number is not None:
            if not KnowledgePage.objects.filter(document=document, number=page_number, status='ready').exists():
                return _error(404, '页面不存在或未处理')
            name, content_type = 'page-{}.png'.format(page_number), 'image/png'
        path = job_path(document.pdf_import.pk, name)
        if not path.is_file():
            return _error(404, '资料文件不可用')
        response = FileResponse(path.open('rb'), content_type=content_type, as_attachment=True,
            filename='{}-{}'.format(document.pk, name))
        response['Cache-Control'] = 'no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    except DatabaseError:
        return _error(503, '资料存储暂时不可用')
