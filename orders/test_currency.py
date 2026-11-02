from decimal import Decimal
from django.test import TestCase, TransactionTestCase
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from .models import OrderInfo
from .analytics import sales_eligible_orders
from .reservations import ReservationError, confirm_payment
from users.models import UserProfile


class CurrencySnapshotTests(TestCase):
    def setUp(self):
        self.user=UserProfile.objects.create(username='currencybuy',is_active=True)

    def order(self,name,**extra):
        return OrderInfo.objects.create(order_id=name,user_profile=self.user,total_amount=10,total_count=1,
            freight=0,status=1,receiver='Synthetic',address='Synthetic',receiver_mobile='000',tag='Test',**extra)

    def test_new_default_and_unknown_excluded_from_comparative_sales(self):
        new=self.order('new');new.status=2;new.save()
        unknown=self.order('old',currency=None);unknown.status=2;unknown.save()
        foreign=self.order('foreign',currency='USD');foreign.status=2;foreign.save()
        self.assertEqual(new.currency,'CNY')
        self.assertEqual(list(OrderInfo.objects.filter(sales_eligible_orders()).values_list('pk',flat=True)),['new'])
        from admin_panel.analytics import build_platform_overview
        summary=build_platform_overview()['summary']
        self.assertEqual(summary['total_flow'],'10.00')
        self.assertEqual(summary['total_sales'],'10.00')
        from orders.checkout_views import result
        self.assertIsNone(result([unknown])['data']['currency'])

    def test_unknown_payment_is_manual_review_without_channel_call(self):
        from pays.service import payment_data
        old=self.order('unknown',currency=None)
        with self.assertRaises(ReservationError) as error:payment_data(old)
        self.assertEqual(error.exception.code,'CURRENCY_REVIEW_REQUIRED')
        confirm_payment(old.pk,'verified-synthetic-trade',Decimal('10'))
        old.refresh_from_db()
        self.assertEqual(old.payment_exception,'currency_review_required')
        self.assertEqual(old.status,1)


class CurrencyMigrationTests(TransactionTestCase):
    def test_nullable_migration_does_not_infer_historical_currency(self):
        executor=MigrationExecutor(connection)
        executor.migrate([('orders','0006_cartcleanuptask')])
        try:
            apps=executor.loader.project_state([('orders','0006_cartcleanuptask')]).apps
            user=apps.get_model('users','UserProfile').objects.create(username='oldcurrency',is_active=True)
            apps.get_model('orders','OrderInfo').objects.create(order_id='HISTORICAL-CURRENCY',user_profile_id=user.pk,
                total_amount='123.45',total_count=1,freight=0,receiver='Synthetic',address='Synthetic',receiver_mobile='000',tag='Test')
            catalog=apps.get_model('goods','Catalog').objects.create(name='Synthetic')
            spu=apps.get_model('goods','SPU').objects.create(name='Synthetic',catalog_id=catalog.pk)
            sku=apps.get_model('goods','SKU').objects.create(name='Synthetic',caption='',spu_id=spu.pk,
                price='11.22',cost_price=1,market_price=20,stock=1)
            item=apps.get_model('orders','OrderGoods').objects.create(order_info_id='HISTORICAL-CURRENCY',
                sku_id=sku.pk,price='11.22',count=1)
            MigrationExecutor(connection).migrate([('orders','0007_order_currency_snapshot')])
            old=OrderInfo.objects.get(pk='HISTORICAL-CURRENCY')
            self.assertIsNone(old.currency)
            self.assertEqual(old.total_amount,Decimal('123.45'))
            from orders.models import OrderGoods
            old_item=OrderGoods.objects.get(pk=item.pk)
            self.assertIsNone(old_item.currency)
            self.assertEqual(old_item.price,Decimal('11.22'))
        finally:
            MigrationExecutor(connection).migrate([('orders','0007_order_currency_snapshot')])
