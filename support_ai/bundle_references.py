"""Resolve only identities from server-saved recommendation plans."""
import re

from .recommendation_options import ORDINAL, number
from .pii import redact

BUNDLE_ID = re.compile(r'^bundle-[0-9a-f]{12}$')
BUNDLE_MENTION = re.compile(r'(?:方案\s*' + ORDINAL + r'|第\s*' + ORDINAL + r'\s*套(?:方案)?)')


def mentioned_bundle(request):
    values = {number(m[1] or m[2]) for m in BUNDLE_MENTION.finditer(request)}
    if len(values) > 1:
        raise ValueError('请一次选择一套方案，或分别说明要查看的商品。')
    return next(iter(values), None)


def bundle_products(source, request='', position=None):
    """Return the selected plan's saved identities, never its historical prices."""
    explicit = mentioned_bundle(request)
    if explicit is not None and position is not None and explicit != position:
        raise ValueError('方案位置不一致，请重新选择。')
    position = explicit if explicit is not None else position
    bundles = source.get('recommendation_bundles') or []
    if position is not None:
        selected = next((b for b in bundles if b.get('position') == position), None)
        if selected is None:
            raise ValueError('当前记录中找不到这套方案，请重新选择。')
        return list(selected.get('items', []))
    selected_id = source.get('selected_bundle_id') or source.get('primary_bundle_id')
    selected = next((b for b in bundles if b.get('bundle_id') == selected_id), None)
    if selected:
        return list(selected.get('items', []))
    if selected_id:
        raise ValueError('所选方案的近期引用已不完整，请重新获取搭配。')
    return list(source.get('recommendations') or source.get('product_references') or [])


def compact_bundle_references(response):
    bundles = []
    for index, bundle in enumerate(response.get('recommendation_bundles', [])[:3], 1):
        if not BUNDLE_ID.fullmatch(str(bundle.get('bundle_id', ''))):
            continue
        products = []
        for pos, item in enumerate(bundle.get('items', [])[:4], 1):
            if type(item.get('sku_id')) is not int or item['sku_id'] <= 0:
                continue
            products.append({'sku_id': item['sku_id']})
            for key in ('name', 'product_name', 'category'):
                if key in item:
                    products[-1][key] = redact(str(item[key]))[:100]
            if type(item.get('quantity')) is int and 1 <= item['quantity'] <= 9007199254740991:
                products[-1]['quantity'] = item['quantity']
            products[-1]['position'] = pos
        bundles.append({'bundle_id': bundle['bundle_id'], 'position': bundle.get('position', index), 'items': products})
    return bundles
