from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('orders', '0006_cartcleanuptask')]
    # Add nullable columns WITHOUT a fill value. The later defaults apply to
    # new application-created rows only, never to unknown historical amounts.
    operations = [
        migrations.AddField(model_name='orderinfo', name='currency',
            field=models.CharField(max_length=3, null=True, blank=True)),
        migrations.AddField(model_name='ordergoods', name='currency',
            field=models.CharField(max_length=3, null=True, blank=True)),
        migrations.AlterField(model_name='orderinfo', name='currency',
            field=models.CharField(max_length=3, null=True, blank=True, default='CNY')),
        migrations.AlterField(model_name='ordergoods', name='currency',
            field=models.CharField(max_length=3, null=True, blank=True, default='CNY')),
    ]
