from django.db import migrations


def install_guards(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute('''
        CREATE FUNCTION ai_validate_embedding() RETURNS trigger AS $$
        DECLARE expected_dimensions integer;
        BEGIN
            IF NEW.embedding IS NOT NULL THEN
                SELECT dimensions INTO expected_dimensions FROM ai_storage_embeddingspace
                    WHERE id = NEW.embedding_space_id FOR SHARE;
                IF expected_dimensions IS NULL OR vector_dims(NEW.embedding) <> expected_dimensions
                    OR vector_norm(NEW.embedding) = 0 THEN
                    RAISE EXCEPTION 'Embedding dimensions or norm do not match its space';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER ai_embedding_guard BEFORE INSERT OR UPDATE ON ai_storage_knowledgechunk
            FOR EACH ROW EXECUTE FUNCTION ai_validate_embedding();

        CREATE FUNCTION ai_preserve_embedding_space() RETURNS trigger AS $$
        BEGIN
            IF ROW(NEW.key, NEW.provider, NEW.model, NEW.revision, NEW.dimensions)
                IS DISTINCT FROM ROW(OLD.key, OLD.provider, OLD.model, OLD.revision, OLD.dimensions)
                AND EXISTS (SELECT 1 FROM ai_storage_knowledgechunk WHERE embedding_space_id = OLD.id) THEN
                RAISE EXCEPTION 'A used embedding space is immutable; create a new version';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER ai_space_guard BEFORE UPDATE ON ai_storage_embeddingspace
            FOR EACH ROW EXECUTE FUNCTION ai_preserve_embedding_space();
    ''')


def remove_guards(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute('''
        DROP TRIGGER IF EXISTS ai_embedding_guard ON ai_storage_knowledgechunk;
        DROP TRIGGER IF EXISTS ai_space_guard ON ai_storage_embeddingspace;
        DROP FUNCTION IF EXISTS ai_validate_embedding();
        DROP FUNCTION IF EXISTS ai_preserve_embedding_space();
    ''')


class Migration(migrations.Migration):
    dependencies = [('ai_storage', '0001_initial')]
    operations = [migrations.RunPython(install_guards, remove_guards)]
