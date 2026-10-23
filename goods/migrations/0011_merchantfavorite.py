from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('goods', '0010_catalog_fallback_image'),
        ('users', '0007_create_customs_user'),
    ]

    operations = [
        migrations.CreateModel(
            name='MerchantFavorite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50)),
                ('logo_url', models.CharField(blank=True, default='', max_length=300)),
                ('created_time', models.DateTimeField(auto_now_add=True)),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name='favorited_by_buyers', to='users.userprofile')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                          related_name='merchant_favorites', to='users.userprofile')),
            ],
            options={
                'db_table': 'goods_merchant_favorite',
                'ordering': ['-created_time', '-id'],
                'unique_together': {('user', 'merchant')},
            },
        ),
    ]
