"""Render platform shells without accessing business services or a business DB."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'support_ai.test_settings'

import django
django.setup()

from django.conf import settings
from django.core.management import get_commands
from django.test import Client
from django.template.loader import render_to_string
import yaml


def main():
    assert settings.DATABASES['default']['NAME'] == ':memory:'
    pages = ['login', 'buyer_dashboard', 'buyer_products', 'buyer_orders', 'buyer_profile',
             'buyer_password', 'buyer_support', 'cart', 'orderConfirm', 'product_details',
             'payment', 'pay_success', 'merchant_dashboard', 'merchant_products',
             'merchant_orders', 'merchant_inventory', 'merchant_settlement',
             'merchant_assistant', 'operations_dashboard', 'logistics_track',
             'admin_panel', 'admin_users', 'admin_agents', 'register_sms']
    forbidden = ['9710', '报关', '清关', 'customs', 'الجمارك', 'الجمرك', 'جمركية']
    client = Client()
    for page in pages:
        response = client.get('/' + page + '.html')
        if response.status_code == 302 and page in ['admin_panel', 'admin_users', 'admin_agents']:
            text = render_to_string(page + '.html').lower()
        else:
            assert response.status_code == 200, (page, response.status_code)
            text = response.content.decode('utf-8').lower()
        for word in forbidden:
            assert word not in text, (page, word)
    for url in ['/customs_9710.html', '/customs_9710.html?embed=1']:
        assert client.get(url).status_code == 404, url
    for filename in ['client/templates/customs_9710.html', 'client/static/js/customs-9710.js',
                     'client/static/css/customs-9710.css',
                     'users/management/commands/create_customs_user.py']:
        assert not (ROOT / filename).exists(), filename
    assert 'create_customs_user' not in get_commands()
    assert 'CUSTOMS_INITIAL_PASSWORD' not in (ROOT / '.env.example').read_text(encoding='utf-8')
    catalog = yaml.safe_load((ROOT / 'docs/sdd/catalog.yaml').read_text(encoding='utf-8'))
    assert len(catalog['modules']) == 8
    capabilities = {row['id'] for row in catalog['capabilities']}
    assert len(capabilities) == 25
    features = yaml.safe_load((ROOT / 'docs/sdd/product/feature-inventory.yaml').read_text(encoding='utf-8'))['features']
    assert len(features) == 34
    for feature in features:
        assert feature['primaryCapability'] in capabilities, feature['id']
    for filename in ['docs/sdd/catalog.yaml', 'docs/sdd/product/feature-inventory.yaml',
                     'docs/sdd/product/open-questions.yaml', 'docs/sdd/product/source-manifest.yaml']:
        yaml.safe_load((ROOT / filename).read_text(encoding='utf-8'))
    print('PASS: 24 page shells, retired routes/assets/command, optional legacy config and SDD maps')


if __name__ == '__main__':
    main()
