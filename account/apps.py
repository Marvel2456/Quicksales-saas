from django.apps import AppConfig
# from procrastinate.contrib.django import app as procrastinate_app


class AccountConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'account'

    # def ready(self):
        # Open the procrastinate app
        # procrastinate_app.open()

        # from . import tasks 
