from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('engagement', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='conversation', name='buyer_hidden',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='conversation', name='merchant_hidden',
            field=models.BooleanField(default=False),
        ),
    ]
