"""Initial payment migration registers references without inventing receipts.

Run only through the isolated PostgreSQL test runner. The original order rows
are compared in full, including unknown currency and historical timestamps.
"""
from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


@skipUnless(connection.vendor == 'postgresql', 'Requires isolated PostgreSQL migrations')
class CombinedPaymentMigrationTests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        self.restore_targets = executor.loader.graph.leaf_nodes()
        self.addCleanup(self.restore_schema)
        # Orders and its risk schema remain at their latest version. Only the
        # new payment schema is removed to exercise its actual initial upgrade.
        executor.migrate([('pays', None), ('orders', '0008_checkout_risk')])
        self.old_apps = executor.loader.project_state(
            [('orders', '0008_checkout_risk')]).apps
        self.User = self.old_apps.get_model('users', 'UserProfile')
        self.Order = self.old_apps.get_model('orders', 'OrderInfo')
        self.user = self.User.objects.create(username='payhistory', is_active=True)

    def restore_schema(self):
        MigrationExecutor(connection).migrate(self.restore_targets)

    def historical_order(self, key, trade_no, currency='CNY', paid=True):
        old_time = timezone.now() - timedelta(days=30)
        return self.Order.objects.create(
            order_id=key, user_profile_id=self.user.pk,
            total_amount=Decimal('123.45'), total_count=3,
            freight=Decimal('8.76'), status=2 if paid else 1,
            currency=currency, reservation_managed=False,
            payment_trade_no=trade_no,
            paid_at=old_time if paid else None,
            expires_at=old_time + timedelta(seconds=900),
            payment_exception='' if paid else 'legacy_payment_review',
            receiver='Synthetic', receiver_mobile='00000000000',
            address='Historical synthetic address', tag='Test',
        )

    def test_initial_upgrade_backfills_only_legacy_references_and_preserves_orders(self):
        known = self.historical_order('history-cny', 'historic-cny')
        unknown = self.historical_order('history-unknown', 'historic-unknown', currency=None)
        foreign = self.historical_order('history-usd', 'historic-usd', currency='USD')
        unconfirmed = self.historical_order('history-unconfirmed', 'historic-unconfirmed', paid=False)
        self.historical_order('history-empty-trade', '')
        self.historical_order('history-null-trade', None)
        before = list(self.Order.objects.order_by('pk').values())

        executor = MigrationExecutor(connection)
        target = ('pays', '0001_initial')
        self.assertIn(('orders', '0008_checkout_risk'),
                      executor.loader.get_migration(*target).dependencies)
        executor.migrate([target])
        apps = executor.loader.project_state([target]).apps
        Receipt = apps.get_model('pays', 'PaymentReceipt')
        Payment = apps.get_model('pays', 'PaymentOrder')
        Allocation = apps.get_model('pays', 'PaymentAllocation')

        self.assertEqual(list(self.Order.objects.order_by('pk').values()), before)
        receipts = {receipt.legacy_order_id: receipt for receipt in Receipt.objects.all()}
        self.assertEqual(set(receipts), {known.pk, unknown.pk, foreign.pk, unconfirmed.pk})
        for order in (known, unknown, foreign, unconfirmed):
            receipt = receipts[order.pk]
            self.assertEqual(receipt.trade_no, order.payment_trade_no)
            self.assertEqual(receipt.amount, Decimal('123.45'))
            self.assertEqual(receipt.currency, order.currency)
            self.assertEqual(receipt.outcome, 'legacy_reference')
            # A historical order's timestamp is not a verified channel receipt
            # time, even when the legacy order already records paid_at.
            self.assertIsNone(receipt.received_at)
            self.assertIsNone(receipt.payment_id)
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(Allocation.objects.exists())
