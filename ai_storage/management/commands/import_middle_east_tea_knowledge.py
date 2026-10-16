import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ai_storage.embeddings import embed_texts
from ai_storage.models import EmbeddingSpace, KnowledgeChunk, KnowledgeDocument


class Command(BaseCommand):
    help = 'Embed curated, source-attributed Middle East tea knowledge with the local Ollama model.'

    def handle(self, *args, **options):
        data_path = Path(__file__).resolve().parents[2] / 'data' / 'middle_east_tea.json'
        records = json.loads(data_path.read_text(encoding='utf-8'))
        if not records:
            raise CommandError('Knowledge dataset is empty.')
        texts = [record['text'] for record in records]
        try:
            vectors = embed_texts(texts)
        except Exception as exc:
            raise CommandError('Local Ollama embedding failed: {}'.format(exc))
        dimensions = len(vectors[0])
        model = settings.AI_OLLAMA_MODEL
        revision = settings.AI_OLLAMA_REVISION
        space_key = settings.AI_EMBEDDING_SPACE_KEY

        with transaction.atomic(using='ai_storage'):
            space, created = EmbeddingSpace.objects.using('ai_storage').get_or_create(
                key=space_key,
                defaults={'provider': 'ollama', 'model': model, 'revision': revision, 'dimensions': dimensions},
            )
            if (space.provider, space.model, space.revision, space.dimensions) != (
                    'ollama', model, revision, dimensions):
                raise CommandError('Embedding space settings changed; choose a new AI_EMBEDDING_SPACE_KEY.')

            counts = {'created': 0, 'updated': 0}
            grouped = {}
            for record, vector in zip(records, vectors):
                grouped.setdefault(record['source_key'], []).append((record, vector))
            for source_key, items in grouped.items():
                first = items[0][0]
                document, created = KnowledgeDocument.objects.using('ai_storage').update_or_create(
                    source_key=source_key,
                    version=1,
                    defaults={
                        'title': first['source_title'],
                        'source_reference': first['source_url'],
                        'status': 'published',
                        'visibility': 'public',
                        'owner_id': None,
                        'metadata': {'region': 'Middle East', 'source_type': first['source_type']},
                    },
                )
                counts['created' if created else 'updated'] += 1
                KnowledgeChunk.objects.using('ai_storage').filter(document=document).delete()
                KnowledgeChunk.objects.using('ai_storage').bulk_create([
                    KnowledgeChunk(
                        document=document,
                        ordinal=ordinal,
                        text=record['text'],
                        metadata={
                            'country': record.get('country'),
                            'topic': record['topic'],
                            'year': record.get('year'),
                            'source_url': record['source_url'],
                        },
                        embedding=vector,
                        embedding_space=space,
                    )
                    for ordinal, (record, vector) in enumerate(items)
                ])
        self.stdout.write(self.style.SUCCESS(
            'Imported {} knowledge chunks into {} ({} dimensions); {} source documents created, {} refreshed.'
            .format(len(records), space_key, dimensions, counts['created'], counts['updated'])
        ))
