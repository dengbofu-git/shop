"""One sellable-stock definition for catalog, carts and checkout."""
from django.db.models import OuterRef, Subquery, Sum, IntegerField, Exists, F, Case, When, Value
from django.db.models.functions import Coalesce
from .models import Inventory


def available_quantity(sku):
    rows = Inventory.objects.filter(sku_id=sku.pk)
    if rows.exists():
        return max(0, rows.filter(warehouse__is_active=True).aggregate(total=Sum('available_quantity'))['total'] or 0)
    return max(0, int(sku.stock or 0))


def with_availability(queryset):
    rows = Inventory.objects.filter(sku_id=OuterRef('pk'))
    totals = rows.filter(warehouse__is_active=True).values('sku_id').annotate(total=Sum('available_quantity')).values('total')
    return queryset.annotate(stock_has_ledger=Exists(rows), stock_ledger_available=Coalesce(Subquery(totals, output_field=IntegerField()),Value(0))).annotate(
        sellable_stock=Case(When(stock_has_ledger=True,then=F('stock_ledger_available')),default=F('stock'),output_field=IntegerField()))
