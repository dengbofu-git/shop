# Generated manually for logistics app

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('orders', '0002_auto_20260218_0147'),
    ]

    operations = [
        migrations.CreateModel(
            name='LogisticsProvider',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, verbose_name='物流公司名称')),
                ('code', models.CharField(max_length=20, unique=True, verbose_name='物流代码')),
                ('api_url', models.URLField(blank=True, null=True, verbose_name='API地址')),
                ('api_key', models.CharField(blank=True, max_length=100, null=True, verbose_name='API密钥')),
                ('contact_phone', models.CharField(blank=True, max_length=20, null=True, verbose_name='联系电话')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否启用')),
                ('created_time', models.DateTimeField(auto_now_add=True)),
                ('updated_time', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'logistics_provider',
                'verbose_name': '物流供应商',
                'verbose_name_plural': '物流供应商',
            },
        ),
        migrations.CreateModel(
            name='ShippingOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tracking_number', models.CharField(max_length=50, unique=True, verbose_name='运单号')),
                ('status', models.SmallIntegerField(choices=[(1, '待发货'), (2, '已发货'), (3, '运输中'), (4, '派送中'), (5, '已签收'), (6, '异常')], default=1, verbose_name='物流状态')),
                ('shipping_fee', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='运费')),
                ('receiver_name', models.CharField(max_length=50, verbose_name='收件人')),
                ('receiver_phone', models.CharField(max_length=20, verbose_name='收件人电话')),
                ('receiver_address', models.CharField(max_length=200, verbose_name='收件地址')),
                ('weight', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='重量(kg)')),
                ('remark', models.TextField(blank=True, null=True, verbose_name='备注')),
                ('created_time', models.DateTimeField(auto_now_add=True)),
                ('updated_time', models.DateTimeField(auto_now=True)),
                ('order_info', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='orders.orderinfo', verbose_name='订单')),
                ('provider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='logistics.logisticsprovider', verbose_name='物流供应商')),
            ],
            options={
                'db_table': 'logistics_shipping_order',
                'verbose_name': '物流订单',
                'verbose_name_plural': '物流订单',
            },
        ),
        migrations.CreateModel(
            name='ShippingTrack',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.SmallIntegerField(verbose_name='状态')),
                ('status_text', models.CharField(max_length=100, verbose_name='状态描述')),
                ('location', models.CharField(blank=True, max_length=100, null=True, verbose_name='位置')),
                ('remark', models.TextField(blank=True, null=True, verbose_name='备注')),
                ('created_time', models.DateTimeField(auto_now_add=True)),
                ('shipping_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='logistics.shippingorder', verbose_name='物流订单')),
            ],
            options={
                'db_table': 'logistics_shipping_track',
                'verbose_name': '物流追踪',
                'verbose_name_plural': '物流追踪',
                'ordering': ['-created_time'],
            },
        ),
    ]
