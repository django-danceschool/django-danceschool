from django.apps import AppConfig
from django.conf import settings


class StripePaymentsAppConfig(AppConfig):
    name = 'danceschool.payments.stripe'
    verbose_name = 'Stripe Functions'

    def ready(self):

        import stripe

        stripe.api_key = getattr(settings,'STRIPE_PRIVATE_KEY','')
