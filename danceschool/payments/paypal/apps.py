# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.conf import settings


class PaypalAppConfig(AppConfig):
    name = 'danceschool.payments.paypal'
    verbose_name = 'Paypal Functions'

    def ready(self):
        # This ensures that the signal receivers are loaded
        import paypalrestsdk

        # Paypal SDK is globally con
        paypalrestsdk.configure({
            'mode': getattr(settings, 'PAYPAL_MODE', 'sandbox'),
            'client_id': getattr(settings, 'PAYPAL_CLIENT_ID',''),
            'client_secret': getattr(settings, 'PAYPAL_CLIENT_SECRET',''),
        })
