"""Trusted application service. Only this layer commits imports, never an Agent."""
from datetime import timedelta
from decimal import Decimal
import hashlib
import uuid

from django.db import transaction
from django.utils import timezone

from inventory.models import Warehouse
from inventory.services import InventoryService
from users.models import UserProfile
from .models import Brand, Catalog, ProductImportJob, SKU, SPU
from .product_import_parser import HEADERS, MAX_BYTES, PARSER_VERSION, ImportFileError, canonical, normalize_row, parse_file


class ImportConflict(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def _active(merchant):
    if not merchant.is_active or not (merchant.is_merchant() or merchant.has_role('supplier')):
        raise ImportConflict('当前账号没有商家导入权限', 403)


def _existing_conflicts(merchant, rows):
    names = [row['data']['name'] for row in rows]
    # Use the database's equality/collation rules as well as Python casefold.
    existing = list(SPU.objects.filter(merchant=merchant, name__in=names).values_list('name', flat=True))
    blocked = {name.casefold() for name in existing}
    for row in rows:
        name = row['data']['name']
        if name.casefold() in blocked or (existing and SPU.objects.filter(merchant=merchant, name=name).exists()):
            row['errors'].append('本店已有同名商品；首期仅新增，请改名或在商品列表中编辑')
    return rows


def _digest(rows):
    return hashlib.sha256((PARSER_VERSION + ':' + canonical(rows)).encode('utf-8')).hexdigest()


def create_job(merchant, filename, content, request_key):
    _active(merchant)
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_BYTES:
        raise ImportFileError('文件不能为空，且不得超过 5 MB')
    try:
        request_key = uuid.UUID(str(request_key))
    except (ValueError, TypeError, AttributeError):
        raise ImportConflict('上传请求编号不正确，请重新选择文件', 400) from None
    checksum = hashlib.sha256(content).hexdigest()
    # Retry with the same request key returns the durable receipt, even after commit.
    with transaction.atomic():
        current = UserProfile.objects.select_for_update().get(pk=merchant.pk)
        _active(current)
        existing = ProductImportJob.objects.filter(merchant=current, request_key=request_key).first()
        if existing:
            if existing.file_sha256 != checksum:
                raise ImportConflict('同一上传编号不能用于不同文件')
            return existing
    # Slow/file-dependent work happens outside the identity row lock.
    rows = parse_file(filename, content)
    with transaction.atomic():
        current = UserProfile.objects.select_for_update().get(pk=merchant.pk)
        _active(current)
        existing = ProductImportJob.objects.filter(merchant=current, request_key=request_key).first()
        if existing:
            if existing.file_sha256 != checksum:
                raise ImportConflict('同一上传编号不能用于不同文件')
            return existing
        _existing_conflicts(current, rows)
        # Never preserve an arbitrary client path or the original file in public storage.
        filename = filename.replace('\\', '/').rsplit('/', 1)[-1][:120]
        return ProductImportJob.objects.create(merchant=current, request_key=request_key,
            filename=filename, file_sha256=checksum, parser_version=PARSER_VERSION,
            review_digest=_digest(rows), status='invalid' if any(r['errors'] for r in rows) else 'ready',
            rows=rows, expires_at=timezone.now() + timedelta(hours=24))


def get_job(merchant, job_id):
    _active(merchant)
    job = ProductImportJob.objects.filter(pk=job_id, merchant=merchant).first()
    if job is None:
        raise ImportConflict('导入任务不存在或不可访问', 404)
    return job


def job_dto(job):
    errors = sum(bool(row['errors']) for row in job.rows)
    # Public-to-the-merchant import contract contains catalog fields only, including
    # when displaying old receipts created before internal costs were removed.
    rows = [{**row, 'data': {key: value for key, value in row['data'].items() if key in HEADERS.values()}}
            for row in job.rows]
    return {'id': str(job.pk), 'filename': job.filename, 'status': job.status,
            'review_digest': job.review_digest, 'expires_at': job.expires_at.isoformat(),
            'expired': job.status != 'committed' and job.expires_at <= timezone.now(),
            'row_count': len(job.rows), 'valid_count': len(job.rows) - errors,
            'error_count': errors, 'rows': rows, 'result': job.result,
            'needs_reupload': job.status != 'committed' and job.parser_version != PARSER_VERSION,
            'currency': 'CNY', 'is_launched': False}


def commit_job(merchant, job_id, review_digest):
    _active(merchant)
    with transaction.atomic():
        # Fixed order: merchant, then job. Serializes this merchant's imports.
        current = UserProfile.objects.select_for_update().get(pk=merchant.pk)
        _active(current)
        job = ProductImportJob.objects.select_for_update().filter(pk=job_id, merchant=current).first()
        if job is None:
            raise ImportConflict('导入任务不存在或不可访问', 404)
        if review_digest != job.review_digest:
            raise ImportConflict('预览版本不匹配，请重新加载后确认')
        if job.status == 'committed':
            return job
        if job.parser_version != PARSER_VERSION or _digest(job.rows) != job.review_digest:
            raise ImportConflict('导入规则或预览已变化，请重新上传文件')
        if job.expires_at <= timezone.now():
            raise ImportConflict('预览已超过 24 小时，请重新上传文件')
        if job.status != 'ready' or not job.rows or any(row['errors'] for row in job.rows):
            raise ImportConflict('文件有错误，须修改后重新上传；本批未导入')
        # Verify typed candidates again rather than accepting browser-supplied rows.
        checked = []
        for row in job.rows:
            data, errors = normalize_row(row['data'])
            if errors or data != row['data']:
                raise ImportConflict('候选数据校验失败，请重新上传')
            checked.append({'data': data, 'errors': [], 'row_number': row['row_number']})
        _existing_conflicts(current, checked)
        if any(row['errors'] for row in checked):
            raise ImportConflict('本店已存在文件中的同名商品，请重新上传检查；本批未导入')
        warehouse, _ = Warehouse.objects.get_or_create(code='DEFAULT',
            defaults={'name': '默认', 'address': '默认仓库'})
        if not warehouse.is_active:
            raise ImportConflict('默认仓库已停用，请联系管理员；本批未导入')
        groups, items = {}, []
        for row in checked:
            data = row['data']
            group = data['name'].casefold()
            if group not in groups:
                catalog, _ = Catalog.objects.get_or_create(name=data['catalog'])
                brand = None
                if data['brand']:
                    brand, _ = Brand.objects.get_or_create(name=data['brand'],
                        defaults={'first_letter': data['brand'][0].upper()[:1]})
                groups[group] = SPU.objects.create(name=data['name'], catalog=catalog,
                    brand=brand, merchant=current, sales=0, comments=0)
            sku = SKU.objects.create(name=data['sku_name'], caption=data['caption'],
                # Legacy schema requires this column. Zero is a compatibility
                # placeholder, not a merchant-provided cost or a profit basis.
                spu=groups[group], price=Decimal(data['price']), cost_price=Decimal('0.00'),
                market_price=Decimal(data['market_price']), stock=0, is_launched=False,
                sales=0, comments=0)
            # Existing inventory service owns initial ledger and stock projection.
            InventoryService.adjust_stock(sku.pk, data['stock'])
            items.append({'row_number': row['row_number'], 'spu_id': sku.spu_id, 'sku_id': sku.pk})
        job.status, job.committed_at = 'committed', timezone.now()
        job.result = {'spu_count': len(groups), 'sku_count': len(items), 'items': items,
                      'is_launched': False}
        job.save(update_fields=['status', 'committed_at', 'result'])
        return job
