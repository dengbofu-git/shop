"""CNY storage/calculation and explicit reference display conversions."""
import json
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path

CONFIG = json.loads(Path(__file__).with_name('currency.json').read_text(encoding='utf-8'))
BASE_CURRENCY = CONFIG['base_currency']
RATES = {code: Decimal(value) for code, value in CONFIG['rates'].items()}


def currency(code=None):
    code = code or BASE_CURRENCY
    if code not in RATES:
        raise ValueError('Unsupported currency')
    return code


def to_base(value, code=None, *, upper=True):
    """Bound conversion: floor upper caps, ceil hard lower bounds; no model FX."""
    return (Decimal(value) / RATES[currency(code)]).quantize(
        Decimal('.01'), rounding=ROUND_FLOOR if upper else ROUND_CEILING)


def display(value, code=None):
    return (Decimal(value) * RATES[currency(code)]).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def money(value, code=None):
    code = currency(code)
    return '{}{}'.format(CONFIG['symbols'][code], format(Decimal(value), '.2f'))


def template_context(request):
    return {'tea_currency': CONFIG}
