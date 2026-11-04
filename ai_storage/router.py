from .database import alias


class AiStorageRouter:
    """One runtime transaction connection; separate aliases only in test fixtures."""

    def db_for_read(self, model, **hints):
        return alias() if model._meta.app_label == 'ai_storage' else None

    def db_for_write(self, model, **hints):
        return alias() if model._meta.app_label == 'ai_storage' else None

    def allow_relation(self, obj1, obj2, **hints):
        labels = (obj1._meta.app_label, obj2._meta.app_label)
        if 'ai_storage' in labels:
            if alias() == 'default':
                return True
            return labels == ('ai_storage', 'ai_storage')
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == 'ai_storage':
            return db == alias()
        if db == 'ai_storage':
            return False
        return None
