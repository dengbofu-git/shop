import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('goods', '0011_merchantfavorite')]
    operations = [migrations.CreateModel(
        name='ProductImportJob',
        fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('request_key', models.UUIDField()),
            ('filename', models.CharField(max_length=120)),
            ('file_sha256', models.CharField(max_length=64)),
            ('parser_version', models.CharField(max_length=40)),
            ('review_digest', models.CharField(max_length=64)),
            ('status', models.CharField(default='ready', max_length=20)),
            ('rows', models.JSONField(default=list)),
            ('result', models.JSONField(default=dict)),
            ('created_time', models.DateTimeField(auto_now_add=True)),
            ('expires_at', models.DateTimeField()),
            ('committed_at', models.DateTimeField(blank=True, null=True)),
            ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='users.userprofile')),
        ],
        options={'db_table': 'goods_product_import_job', 'constraints': [models.UniqueConstraint(
            fields=('merchant', 'request_key'), name='goods_import_merchant_request')]},
    )]
