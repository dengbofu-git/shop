from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('support_ai', '0003_agent_reranking')]

    operations = [
        migrations.AddField(
            model_name='supportconversation', name='active_order_id',
            field=models.CharField(max_length=64, blank=True, default=''),
        ),
        migrations.AddField(
            model_name='supportconversation', name='active_order_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
