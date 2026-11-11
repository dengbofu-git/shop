import uuid

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('ai_storage', '0004_hybrid_search')]

    operations = [
        migrations.CreateModel(
            name='BuyerPreferenceState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('owner_id', models.PositiveBigIntegerField(unique=True)),
                ('revision', models.PositiveBigIntegerField(default=0)),
                ('reset_at', models.DateTimeField(blank=True, null=True)),
                ('field_fences', models.JSONField(default=dict)),
                ('records', models.JSONField(default=dict)),
                ('projection_hash', models.CharField(blank=True, max_length=64)),
                ('behavior_generation', models.PositiveBigIntegerField(default=0)),
                ('behavior_applied_generation', models.PositiveBigIntegerField(default=0)),
                ('behavior_fingerprint', models.CharField(blank=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='PreferenceUpdateJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('event_key', models.CharField(max_length=200, unique=True)),
                ('owner_id', models.PositiveBigIntegerField()),
                ('source_type', models.CharField(choices=[('chat', 'chat'), ('behavior', 'behavior')], max_length=12)),
                ('source_ref', models.CharField(max_length=200)),
                ('source_at', models.DateTimeField(blank=True, null=True)),
                ('payload', models.JSONField(default=dict)),
                ('results', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('queued', 'queued'), ('running', 'running'), ('done', 'done'), ('dead', 'dead')], default='queued', max_length=12)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('lease_token', models.UUIDField(blank=True, null=True)),
                ('lease_until', models.DateTimeField(blank=True, null=True)),
                ('available_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('error_code', models.CharField(blank=True, max_length=60)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'indexes': [models.Index(fields=['status', 'available_at', 'lease_until'], name='ai_profile_job_ready')],
                'constraints': [
                    models.CheckConstraint(condition=models.Q(source_type__in=['chat', 'behavior']), name='ai_profile_job_source'),
                    models.CheckConstraint(condition=models.Q(status__in=['queued', 'running', 'done', 'dead']), name='ai_profile_job_status'),
                ],
            },
        ),
        migrations.CreateModel(
            name='PreferenceAudit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('owner_id', models.PositiveBigIntegerField()),
                ('source_type', models.CharField(max_length=12)),
                ('source_ref', models.CharField(max_length=200)),
                ('source_at', models.DateTimeField(blank=True, null=True)),
                ('record_key', models.CharField(blank=True, max_length=80)),
                ('outcome', models.CharField(max_length=12)),
                ('reason', models.CharField(max_length=60)),
                ('candidate', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'indexes': [models.Index(fields=['owner_id', 'created_at'], name='ai_profile_owner_trace')]},
        ),
    ]
