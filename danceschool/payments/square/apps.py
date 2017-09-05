# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.conf import settings


class SquareAppConfig(AppConfig):
    name = 'danceschool.payments.square'
    verbose_name = 'Square Functions'

    def ready(self):
        import squareconnect
        squareconnect.configuration.access_token = getattr(settings,'SQUARE_ACCESS_TOKEN','')
