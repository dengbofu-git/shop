class AiStorageRouter:
    """PostgreSQL owns AI storage; business models stay on the default MySQL."""

    def db_for_read(self, model, **hints):
        return 'ai_storage' if model._meta.app_label == 'ai_storage' else None

    def db_for_write(self, model, **hints):
        return 'ai_storage' if model._meta.app_label == 'ai_storage' else None

    def allow_relation(self, obj1, obj2, **hints):
        labels = (obj1._meta.app_label, obj2._meta.app_label)
        if 'ai_storage' in labels:
            return labels == ('ai_storage', 'ai_storage')
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == 'ai_storage':
            return db == 'ai_storage'
        if db == 'ai_storage':
            return False
        return None
