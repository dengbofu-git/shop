"""One image priority for storefront, cart and order representations."""
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from .models import SKU, SKUImage


@dataclass(frozen=True)
class ProductImage:
    path: Path
    is_virtual: bool = False

    @property
    def name(self):
        return self.path.relative_to(Path(settings.MEDIA_ROOT).resolve()).as_posix()


def _existing_file(path):
    if not path:
        return None
    try:
        root = Path(settings.MEDIA_ROOT).resolve()
        candidate = Path(path).resolve()
        candidate.relative_to(root)
        if candidate.is_file() and candidate.stat().st_size:
            return candidate
    except (OSError, ValueError, TypeError):
        pass
    return None


def _field_file(field):
    if not field or not field.name:
        return None
    return _existing_file(Path(settings.MEDIA_ROOT) / field.name.replace('\\', '/'))


def _uploaded_file(sku):
    file = _field_file(sku.default_image_url)
    if file:
        return file
    # A broken default or first gallery file must not hide a later valid upload.
    for field in SKUImage.objects.filter(sku_id=sku.id).order_by('id').values_list('image', flat=True):
        file = _existing_file(Path(settings.MEDIA_ROOT) / field)
        if file:
            return file
    directory = Path(settings.MEDIA_ROOT) / 'sku' / str(sku.id)
    if directory.is_dir():
        for file in sorted(directory.iterdir()):
            if file.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
                existing = _existing_file(file)
                if existing:
                    return existing
    for extension in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
        file = _existing_file(Path(settings.MEDIA_ROOT) / 'sku' / f'{sku.id}.{extension}')
        if file:
            return file
    return None


def resolve_sku_image(sku):
    """Real SKU/gallery/legacy files, same-SPU real photo, then catalog virtual art."""
    file = _uploaded_file(sku)
    if file:
        return ProductImage(file)
    # Preserve the established sharing of real product photos between specifications.
    for other in SKU.objects.filter(spu_id=sku.spu_id).exclude(id=sku.id).order_by('id'):
        file = _uploaded_file(other)
        if file:
            return ProductImage(file)
    file = _field_file(sku.spu.catalog.fallback_image)
    return ProductImage(file, is_virtual=True) if file else None


def sku_image_name(sku):
    image = resolve_sku_image(sku)
    return image.name if image else ''
