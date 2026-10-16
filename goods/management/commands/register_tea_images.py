"""Register generated catalog art without changing any SKU upload fields."""
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image

from goods.models import Catalog


class Command(BaseCommand):
    help = '登记茶类虚拟默认图；默认仅预览，--apply 执行，已有不同默认图须显式 --replace。'

    def add_arguments(self, parser):
        parser.add_argument('--manifest', required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--replace', action='store_true')

    def handle(self, *args, **options):
        try:
            manifest = json.loads(Path(options['manifest']).read_text(encoding='utf-8'))
            entries = manifest['entries']
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(f'无法读取图片清单: {exc}')
        root = Path(settings.MEDIA_ROOT).resolve()
        registrations = []
        seen = set()
        for entry in entries:
            name, file = entry['name'], entry['file']
            if name in seen:
                raise CommandError(f'重复茶类: {name}')
            seen.add(name)
            target = (root / file).resolve()
            try:
                target.relative_to(root)
                content = target.read_bytes()
                with Image.open(target) as image:
                    image.verify()
            except (OSError, ValueError) as exc:
                raise CommandError(f'图片不可用 {file}: {exc}')
            if hashlib.sha256(content).hexdigest() != entry['sha256']:
                raise CommandError(f'图片哈希不匹配: {file}')
            catalogs = list(Catalog.objects.filter(name=name))
            if not catalogs:
                raise CommandError(f'数据库不存在茶类: {name}')
            for catalog in catalogs:
                if catalog.fallback_image and catalog.fallback_image.name != file and not options['replace']:
                    raise CommandError(f'{name}已有默认图；如需替换请显式使用--replace')
                registrations.append((catalog, target.relative_to(root).as_posix()))
        if options['apply']:
            with transaction.atomic():
                for catalog, file in registrations:
                    Catalog.objects.filter(pk=catalog.pk).update(fallback_image=file)
        for catalog, file in registrations:
            self.stdout.write(f'{catalog.id} {catalog.name}: {file}')
        self.stdout.write(self.style.SUCCESS(
            f'{"已登记" if options["apply"] else "预览"} {len(registrations)} 个茶类；SKU真实图片字段未修改。'
        ))
