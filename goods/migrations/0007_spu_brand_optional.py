# Generated manually - SPU brand 可选

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('goods', '0006_sku_is_recommended'),
    ]

    operations = [
        migrations.AlterField(
            model_name='spu',
            name='brand',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='goods.brand', verbose_name='品牌'),
        ),
    ]
