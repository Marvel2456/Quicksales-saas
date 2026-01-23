from django.apps import AppConfig


class ImsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ims'
    
    def ready(self):
        import ims.signals
