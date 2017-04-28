from django.apps import AppConfig


class DiscountsAppConfig(AppConfig):
    name = 'danceschool.discounts'
    verbose_name = 'Discount System Functions'

    def ready(self):
        # This ensures that the signal receivers are loaded
        from . import handlers
