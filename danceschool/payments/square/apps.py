# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig


class SquareAppConfig(AppConfig):
    name = 'danceschool.payments.square'
    verbose_name = 'Square Functions'
