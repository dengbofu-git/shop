from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from ai_storage.models import BuyerMemory
from support_ai.contracts import Preferences
from support_ai.models import SupportPreference


class Command(BaseCommand):
    help = 'Copy legacy MySQL buyer preferences to PostgreSQL without deleting or overwriting data.'

    def handle(self, *args, **options):
        source = connections['default']
        if SupportPreference._meta.db_table not in source.introspection.table_names():
            self.stdout.write('No legacy preference table; nothing to transfer.')
            return
        created = skipped = 0
        for row in SupportPreference.objects.using('default').order_by('pk').iterator(chunk_size=200):
            try:
                data = Preferences.model_validate(row.preferences).model_dump()
            except ValueError:
                raise CommandError('Legacy preferences contain invalid data; transfer stopped without deleting the source.')
            _, inserted = BuyerMemory.objects.get_or_create(owner_id=row.user_id, defaults={'preferences': data})
            created += int(inserted)
            skipped += int(not inserted)
        self.stdout.write('Transferred {}; preserved {} existing PostgreSQL memories. MySQL source retained.'.format(created, skipped))
