from django.db import migrations, models


def ensure_unicode_nickname(apps, schema_editor):
    # Existing schemas may default to MySQL utf8mb3. Change only the new
    # display-name column; other account columns and existing data stay intact.
    if schema_editor.connection.vendor == 'mysql':
        table = schema_editor.quote_name(apps.get_model('users', 'UserProfile')._meta.db_table)
        column = schema_editor.quote_name('nickname')
        schema_editor.execute('ALTER TABLE %s MODIFY %s varchar(30) CHARACTER SET utf8mb4 '
                              'COLLATE utf8mb4_unicode_ci NOT NULL' % (table, column))


class Migration(migrations.Migration):
    atomic = False  # MySQL column charset DDL cannot run inside a transaction.
    dependencies = [('users', '0007_create_customs_user')]

    operations = [
        migrations.AddField(
            model_name='userprofile', name='nickname',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='昵称'),
        ),
        # No reverse charset conversion: that could lose saved emoji. Removing
        # this new field is a separate, explicitly approved rollback operation.
        migrations.RunPython(ensure_unicode_nickname, migrations.RunPython.noop),
    ]
