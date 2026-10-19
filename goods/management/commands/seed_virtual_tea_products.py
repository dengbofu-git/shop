"""Add one explicit, auditable batch of 100 fully related fictional tea products."""
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.apps import apps
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

from goods.models import (Brand, Catalog, ProductAttribute, ProductAttributeValue, ProductTemplate,
                          SaleAttrValue, SKU, SKUSpecValue, SPU, SPUSaleAttr, SPUSpec)
from inventory.models import Inventory, InventoryLog, Warehouse
from users.models import UserProfile


FAMILIES = [
    ('green', '绿茶', '虚拟青岚茶社', 'Q', '青岚', '7.80', 18, 82,
     '春露 云芽 竹影 晴岚 溪翠 晨曦 山风 雨青 碧潭 柳烟 石泉 松月 露华 清溪 林语 翠谷 春汀 鹿鸣 岚光 碧野'),
    ('black', '红茶', '虚拟赤霞茶坊', 'C', '赤霞', '6.50', 24, 92,
     '朝霞 暖阳 金穗 桂影 秋岚 红韵 晚晴 星火 琥珀 麦香 云锦 晨光 枫语 山岚 夕照 丹露 醇风 花丘 远山 云杉'),
    ('oolong', '乌龙茶', '虚拟云岭茶庄', 'Y', '云岭', '9.60', 24, 95,
     '岩语 兰溪 山韵 焙月 云峰 松涛 花涧 青岩 岚谷 清音 岩泉 雾岭 桂岚 秋涧 林泉 月岩 鹤鸣 山岫 澄香 霁峰'),
    ('white', '白茶', '虚拟白汀茶舍', 'B', '白汀', '10.80', 36, 90,
     '月白 银露 晴雪 芦汀 星芽 素岚 白鹿 云棉 晨霜 清羽 雪溪 秋白 鹤影 露汀 山雪'),
    ('yellow', '黄茶', '虚拟金露茶集', 'J', '金露', '11.50', 18, 85,
     '金芽 黄露 晴穗 谷香 暖岚 金汀 山穗 秋金 露穗 麦月'),
    ('dark', '黑茶', '虚拟墨山茶仓', 'M', '墨山', '8.20', 60, 98,
     '墨韵 陈岚 山藏 暖木 岩藏 深林 秋仓 古径 山醇 石韵 云仓 沉香 谷藏 林藏 远岫'),
]

ATTRIBUTES = [
    ('batch', '虚拟数据批次', 'text'), ('virtual', '是否虚拟商品', 'boolean'),
    ('country', '模拟产地国家', 'text'), ('region', '模拟产区', 'text'),
    ('weight', '净含量（克）', 'number'), ('package', '包装形式', 'select'),
    ('form', '茶叶形态', 'select'), ('grade', '模拟等级', 'select'),
    ('ingredients', '模拟配料', 'text'), ('flavor', '模拟口感', 'text'),
    ('aroma', '模拟香气', 'text'), ('usage', '模拟适用场景', 'multiselect'),
    ('season', '模拟采摘季节', 'select'), ('production', '模拟生产日期', 'date'),
    ('shelf_life', '模拟保质期（月）', 'number'), ('temperature', '模拟冲泡水温（℃）', 'number'),
    ('brew_time', '模拟冲泡时长（秒）', 'number'), ('storage', '储存说明', 'text'),
    ('currency', '计价币种', 'select'), ('unit_price', '每100克单价（USD）', 'number'),
    ('vessel', '模拟冲泡器具', 'select'), ('traceability', '虚拟追溯说明', 'text'),
    ('roast', '模拟焙火程度', 'select'), ('lot', '虚拟批号', 'text'),
    ('minimum_order', '最小采购数量', 'number'),
]


def build_products(batch, as_of):
    products = []
    usages = ['日常饮用', '办公室饮用', '礼赠演示', '调饮演示', '餐饮采购演示']
    packages = ['密封袋装', '金属罐装', '双罐礼盒', '独立茶包盒', '大袋装']
    weights = [100, 150, 200, 50, 500]
    flavors = ['清爽回甘', '柔和醇润', '饱满顺滑', '清淡鲜爽', '浓醇厚实']
    aromas = ['清香', '花香', '熟果香', '谷物香', '木质香']
    for slug, category, brand, initial, region, base, shelf, temperature, names in FAMILIES:
        for position, variety in enumerate(names.split()):
            index = len(products) + 1
            slot = position % 5
            grade_index = (position // 5) % 3
            grade = ['优选级', '精品级', '特选级'][grade_index]
            weight = weights[slot]
            price = (Decimal(base) * Decimal(weight) / 100 * [Decimal('1'), Decimal('1.25'), Decimal('1.55')][grade_index]
                     + [Decimal('1.20'), Decimal('3.00'), Decimal('8.00'), Decimal('2.00'), Decimal('2.50')][slot]).quantize(Decimal('.01'))
            production = as_of - timedelta(days=15 + index % 60)
            item = {'index': index, 'family': slug, 'category': category, 'brand': brand,
                    'initial': initial, 'region': region, 'name': '【虚拟】{}·{}{}'.format(region, variety, category),
                    'specification': '{}g·{}·{}'.format(weight, packages[slot], grade),
                    'price': price, 'cost_price': (price * Decimal('.58')).quantize(Decimal('.01')),
                    'market_price': (price * Decimal('1.20')).quantize(Decimal('.01')),
                    'stock': 120 + index * 37 % 880, 'weight': weight, 'package': packages[slot],
                    'grade': grade, 'flavor': flavors[(position + grade_index) % 5], 'usage': usages[slot]}
            item['caption'] = '【虚拟测试】{}；{}；{}；非真实在售商品。'.format(batch, item['usage'], item['flavor'])
            item['attributes'] = {
                'batch': batch, 'virtual': True, 'country': '虚拟中国', 'region': region + '虚拟示范区',
                'weight': weight, 'package': packages[slot], 'form': '茶包' if slot == 3 else '散叶茶',
                'grade': grade, 'ingredients': '模拟茶叶100%（虚拟数据）', 'flavor': item['flavor'],
                'aroma': aromas[(position + 1) % 5], 'usage': item['usage'],
                'season': ['春季', '夏季', '秋季'][position % 3], 'production': production,
                'shelf_life': shelf, 'temperature': temperature, 'brew_time': 60 + position % 4 * 30,
                'storage': '模拟储存要求：密封、干燥、避光，远离异味。', 'currency': 'USD',
                'unit_price': (price / weight * 100).quantize(Decimal('.01')),
                'vessel': ['玻璃杯', '盖碗', '茶壶'][position % 3],
                'traceability': '仅供本地功能演示，批次{}，不代表真实产地、检测或认证。'.format(batch),
                'roast': ['轻焙', '中焙', '重焙'][position % 3],
                'lot': '{}-{:03d}'.format(batch, index), 'minimum_order': 1 if slot != 4 else 5,
            }
            products.append(item)
    if len(products) != 100 or len({p['name'] for p in products}) != 100:
        raise CommandError('The batch must contain exactly 100 distinct products')
    return products


class Command(BaseCommand):
    help = 'Create 100 clearly fictional tea SPUs/SKUs, attributes and balanced initial inventory.'

    def add_arguments(self, parser):
        parser.add_argument('--merchant-id', type=int, required=True)
        parser.add_argument('--expected-database-name', required=True)
        parser.add_argument('--expected-server-uuid', required=True)
        parser.add_argument('--batch', default='VTEA-20261016')
        parser.add_argument('--as-of', default='2026-10-16')
        parser.add_argument('--report-dir', default='reports/virtual-products/2026-10-16')
        parser.add_argument('--database', default='default')

    def handle(self, *args, **options):
        alias = options['database']
        if alias != 'default' or connections[alias].vendor != 'mysql':
            raise CommandError('This command requires the business MySQL default database')
        batch = options['batch']
        if not batch.replace('-', '').isalnum() or len(batch) > 24:
            raise CommandError('Use an alphanumeric/hyphen batch code of at most 24 characters')
        with connections[alias].cursor() as cursor:
            cursor.execute('SELECT DATABASE(), @@server_uuid')
            database, server_uuid = cursor.fetchone()
        if database != options['expected_database_name'] or server_uuid != options['expected_server_uuid']:
            raise CommandError('Unexpected database identity; no rows were written')
        merchant = UserProfile.objects.using(alias).filter(pk=options['merchant_id'], user_type='merchant', is_active=True).first()
        if merchant is None:
            raise CommandError('An existing active merchant is required')
        products = build_products(batch, date.fromisoformat(options['as_of']))
        directory = Path(options['report_dir']).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        prefix = '【虚拟测试】{}；'.format(batch)
        existing = list(SKU.objects.using(alias).filter(caption__startswith=prefix).select_related('spu'))
        if existing:
            if len(existing) == 100 and len({s.spu_id for s in existing}) == 100 and all(s.spu.merchant_id == merchant.pk for s in existing):
                self.stdout.write('Batch already exists: 100 products; no rows changed.')
                return
            raise CommandError('Incomplete or conflicting batch exists; no rows changed')
        models = list(apps.get_app_config('goods').get_models()) + [Warehouse, Inventory, InventoryLog]
        before = {model._meta.label: list(model.objects.using(alias).values()) for model in models}
        before[SKU.sale_attr_value.through._meta.label] = list(SKU.sale_attr_value.through.objects.using(alias).values())
        backup = directory / (batch + '-before.json')
        with backup.open('x', encoding='utf-8') as stream:
            json.dump({'database': database, 'server_uuid': server_uuid, 'tables': before}, stream, ensure_ascii=False, indent=2, default=str)
        (directory / (batch + '-plan.json')).write_text(json.dumps(products, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        referenced = defaultdict(set)
        created = defaultdict(list)

        def create(model, **fields):
            obj = model(**fields)
            obj.full_clean()
            obj.save(using=alias)
            created[model._meta.label].append(obj.pk)
            referenced[model._meta.label].add(obj.pk)
            return obj

        code_prefix = 'vtea_' + hashlib.sha256(batch.encode()).hexdigest()[:8]
        rows = []
        with transaction.atomic(using=alias):
            UserProfile.objects.using(alias).select_for_update().get(pk=merchant.pk)
            if SKU.objects.using(alias).filter(caption__startswith=prefix).exists():
                raise CommandError('Batch was concurrently created; transaction stopped')
            warehouse = create(Warehouse, name='【虚拟】茶品演示仓', code=batch + '-WH',
                address='虚拟测试仓地址，仅用于本地功能演示', province='虚拟省', city='虚拟市',
                contact_person='虚拟测试联系人', contact_phone='00000000000', is_active=True)
            families = {}
            for slug, category_name, brand_name, initial, region, base, shelf, temperature, names in FAMILIES:
                category = Catalog.objects.using(alias).filter(name=category_name).order_by('id').first()
                if category is None:
                    category = create(Catalog, name=category_name)
                referenced[Catalog._meta.label].add(category.pk)
                brand = create(Brand, name=brand_name, first_letter=initial, logo='')
                template = create(ProductTemplate, name='【虚拟】{}模板-{}'.format(category_name, batch),
                    catalog=category, description='虚拟商品完整属性模板；所有产地、口感及工艺数据仅用于演示。', is_active=True)
                attributes = {}
                for sort, (key, name, kind) in enumerate(ATTRIBUTES):
                    attributes[key] = create(ProductAttribute, template=template, catalog=category, name=name,
                        code='{}_{}_{}'.format(code_prefix, slug, key), attribute_type=kind,
                        is_required=True, is_filterable=kind in ('select', 'multiselect', 'number', 'boolean'),
                        is_searchable=kind in ('text', 'select', 'multiselect'), sort_order=sort)
                families[slug] = (category, brand, attributes)
            for item in products:
                category, brand, attributes = families[item['family']]
                spu = create(SPU, name=item['name'], sales=0, comments=0, brand=brand, catalog=category, merchant=merchant)
                sku = create(SKU, name=item['specification'], caption=item['caption'], spu=spu,
                    price=item['price'], cost_price=item['cost_price'], market_price=item['market_price'],
                    stock=item['stock'], sales=0, comments=0, is_launched=True,
                    is_recommended=item['index'] % 8 == 0, default_image_url='', version=0)
                for name, value in [('净含量', '{}g'.format(item['weight'])), ('包装形式', item['package']), ('等级', item['grade'])]:
                    sale_attr = create(SPUSaleAttr, spu=spu, name=name)
                    sale_value = create(SaleAttrValue, spu_sale_attr=sale_attr, name=value)
                    sku.sale_attr_value.add(sale_value)
                    spec = create(SPUSpec, spu=spu, name=name)
                    create(SKUSpecValue, sku=sku, spu_spec=spec, name=value)
                for key, name, kind in ATTRIBUTES:
                    value = item['attributes'][key]
                    fields = {'value_text': None, 'value_number': None, 'value_boolean': None, 'value_date': None}
                    field = {'number': 'value_number', 'boolean': 'value_boolean', 'date': 'value_date'}.get(kind, 'value_text')
                    fields[field] = Decimal(str(value)) if kind == 'number' else value
                    create(ProductAttributeValue, attribute=attributes[key], spu=spu, sku=sku, **fields)
                ledger = create(Inventory, sku=sku, warehouse=warehouse, quantity=item['stock'], reserved_quantity=0,
                                available_quantity=item['stock'], min_stock=20)
                create(InventoryLog, sku=sku, warehouse=warehouse, log_type='in', quantity=item['stock'],
                       before_quantity=0, after_quantity=item['stock'], remark='虚拟初始入库；批次' + batch,
                       operator='seed:' + batch)
                if sku.stock != ledger.available_quantity or sku.sale_attr_value.count() != 3:
                    raise CommandError('Unbalanced inventory or incomplete sale attributes')
                rows.append({'sku_id': sku.pk, 'spu_id': spu.pk, 'name': spu.name, 'category': category.name,
                             'specification': sku.name, 'price_usd': str(sku.price), 'stock': sku.stock, 'usage': item['usage']})
                if len(rows) % 20 == 0:
                    self.stdout.write('Prepared {}/100 products within transaction'.format(len(rows)))
                    self.stdout.flush()
            if (len(rows) != 100 or SKU.objects.using(alias).filter(pk__in=[r['sku_id'] for r in rows]).count() != 100
                    or ProductAttributeValue.objects.using(alias).filter(sku_id__in=[r['sku_id'] for r in rows]).count() != 2500):
                raise CommandError('Incomplete generated batch; rolling back')
        fixtures = []
        for model in models:
            ids = referenced.get(model._meta.label, set())
            if ids:
                fixtures.extend(json.loads(serializers.serialize('json', model.objects.using(alias).filter(pk__in=ids))))
        fixtures.extend(json.loads(serializers.serialize('json', SKU.sale_attr_value.through.objects.using(alias).filter(sku_id__in=[r['sku_id'] for r in rows]))))
        (directory / (batch + '-fixture.json')).write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding='utf-8')
        manifest = {'batch': batch, 'database': database, 'server_uuid': server_uuid, 'merchant_id': merchant.pk,
                    'created_counts': {key: len(values) for key, values in created.items()}, 'created_ids': dict(created),
                    'category_counts': dict(Counter(row['category'] for row in rows)), 'products': rows,
                    'backup': backup.name, 'attribute_count_per_sku': len(ATTRIBUTES), 'images_generated': False}
        (directory / (batch + '-manifest.json')).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = ['# 100 种虚拟茶商品', '', '批次：{}。每种独立 SPU 配一个 SKU；所有商品及属性为虚拟测试数据。'.format(batch), '',
                 '| SKU | 商品 | 茶类 | 规格 | USD 单价 | 可用库存 | 模拟场景 |', '|---:|---|---|---|---:|---:|---|']
        for row in rows:
            lines.append('| {sku_id} | {name} | {category} | {specification} | {price_usd} | {stock} | {usage} |'.format(**row))
        lines += ['', '完整字段与外键、时间戳、规格关联、类型属性和库存记录见同目录 fixture.json；类型不适用的属性值列保留 NULL，图片字段留空。',
                  '销售与评价计数初始化为 0。批次重复执行不会追加商品。原有商品未修改。', '']
        (directory / 'catalog.md').write_text('\n'.join(lines), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('Created 100 SPUs, 100 SKUs, 2500 attribute values and balanced inventory.'))
        self.stdout.write(json.dumps(manifest['category_counts'], ensure_ascii=False))
        self.stdout.write('Reports: ' + str(directory))
