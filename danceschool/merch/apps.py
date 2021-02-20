from django.apps import AppConfig


class MerchAppConfig(AppConfig):
    name = 'danceschool.merch'

    def ready(self):
        # Ensure that signal handlers are loaded
        from . import handlers
