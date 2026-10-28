from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import migrations, models


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute('''
        INSERT INTO ai_storage_knowledgerevision (id, revision) VALUES (1, 1);
        CREATE FUNCTION ai_search_terms(value text) RETURNS text AS $$
          SELECT coalesce(value, '') || ' ' || coalesce((
            SELECT string_agg(substr(parts[1], n, 2), ' ')
            FROM regexp_matches(coalesce(value, ''), '[一-鿿]+', 'g') AS parts,
                 LATERAL generate_series(1, greatest(char_length(parts[1])-1, 1)) AS n
          ), '');
        $$ LANGUAGE SQL IMMUTABLE PARALLEL SAFE;
        CREATE FUNCTION ai_index_chunk() RETURNS trigger AS $$
        DECLARE title_value text;
        BEGIN
          SELECT title INTO title_value FROM ai_storage_knowledgedocument WHERE id=NEW.document_id;
          NEW.search_text := coalesce(title_value, '') || E'\n' ||
             coalesce(NEW.metadata->>'section_path', '') || E'\n' || NEW.text;
          NEW.search_vector := to_tsvector('simple', ai_search_terms(NEW.search_text));
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER ai_chunk_search BEFORE INSERT OR UPDATE ON ai_storage_knowledgechunk
          FOR EACH ROW EXECUTE FUNCTION ai_index_chunk();
        CREATE FUNCTION ai_refresh_document_search() RETURNS trigger AS $$
        BEGIN
          IF NEW.title IS DISTINCT FROM OLD.title THEN
            UPDATE ai_storage_knowledgechunk SET text=text WHERE document_id=NEW.id;
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER ai_document_search AFTER UPDATE ON ai_storage_knowledgedocument
          FOR EACH ROW EXECUTE FUNCTION ai_refresh_document_search();
        CREATE FUNCTION ai_bump_knowledge_revision() RETURNS trigger AS $$
        BEGIN
          INSERT INTO ai_storage_knowledgerevision (id, revision) VALUES (1, 1)
            ON CONFLICT (id) DO UPDATE SET revision=ai_storage_knowledgerevision.revision+1;
          RETURN NULL;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER ai_chunks_revision AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE
          ON ai_storage_knowledgechunk FOR EACH STATEMENT EXECUTE FUNCTION ai_bump_knowledge_revision();
        CREATE TRIGGER ai_documents_revision AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE
          ON ai_storage_knowledgedocument FOR EACH STATEMENT EXECUTE FUNCTION ai_bump_knowledge_revision();
        CREATE TRIGGER ai_spaces_revision AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE
          ON ai_storage_embeddingspace FOR EACH STATEMENT EXECUTE FUNCTION ai_bump_knowledge_revision();
        UPDATE ai_storage_knowledgechunk SET text=text;
    ''')


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute('''
        DROP TRIGGER ai_spaces_revision ON ai_storage_embeddingspace;
        DROP TRIGGER ai_documents_revision ON ai_storage_knowledgedocument;
        DROP TRIGGER ai_chunks_revision ON ai_storage_knowledgechunk;
        DROP TRIGGER ai_document_search ON ai_storage_knowledgedocument;
        DROP TRIGGER ai_chunk_search ON ai_storage_knowledgechunk;
        DROP FUNCTION ai_bump_knowledge_revision();
        DROP FUNCTION ai_refresh_document_search();
        DROP FUNCTION ai_index_chunk();
        DROP FUNCTION ai_search_terms(text);
    ''')


class Migration(migrations.Migration):
    dependencies = [('ai_storage', '0003_pdf_import_pipeline')]
    operations = [
        migrations.AddField('knowledgechunk', 'search_text', models.TextField(default='', editable=False)),
        migrations.AddField('knowledgechunk', 'search_vector', SearchVectorField(null=True, editable=False)),
        migrations.AddIndex('knowledgechunk', GinIndex(fields=['search_vector'], name='ai_chunk_search_gin')),
        migrations.CreateModel(name='KnowledgeRevision', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('revision', models.PositiveBigIntegerField(default=1)),
        ]),
        migrations.RunPython(install, uninstall),
    ]
