from django.db import migrations, models
from django.db.models.functions import Upper


class Migration(migrations.Migration):
    dependencies = [('users', '0008_userprofile_nickname')]
    operations = [
        migrations.AddConstraint(
            model_name='userprofile',
            constraint=models.UniqueConstraint(Upper('username'), name='users_username_case_unique'),
        ),
    ]
