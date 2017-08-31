from django.core.management.base import BaseCommand
from django.apps import apps
from django.conf import settings

from six.moves import input

try:
    import readline
except ImportError:
    pass


class Command(BaseCommand):
    help = 'Check Stripe settings and created necessary placeholders for Stripe Checkout integration.'

    def boolean_input(self, question, default=None):
        '''
        Method for yes/no boolean inputs
        '''
        result = input("%s: " % question)
        if not result and default is not None:
            return default
        while len(result) < 1 or result[0].lower() not in "yn":
            result = input("Please answer yes or no: ")
        return result[0].lower() == "y"

    def handle(self, *args, **options):

        from cms.api import add_plugin
        from cms.models import Page, StaticPlaceholder

        try:
            initial_language = settings.LANGUAGES[0][0]
        except IndexError:
            initial_language = getattr(settings, 'LANGUAGE_CODE', 'en')

        # Do some sanity checks to ensure that necessary apps are listed in INSTALLED_APPS
        # before proceeding
        required_apps = [
            ('cms', 'Django CMS'),
            ('danceschool.core', 'Core danceschool app'),
            ('danceschool.payments.stripe', 'Stripe integration app'),
        ]
        for this_app in required_apps:
            if not apps.is_installed(this_app[0]):
                self.stdout.write(self.style.ERROR('ERROR: %s is not installed or listed in INSTALLED_APPS. Please install before proceeding.' % this_app[1]))
                return None

        self.stdout.write(
            """
CHECKING STRIPE INTEGRATION
---------------------------
            """
        )

        client_id = getattr(settings,'STRIPE_PUBLIC_KEY','')
        client_secret = getattr(settings,'STRIPE_PRIVATE_KEY','')

        if client_id:
            self.stdout.write('Stripe public key set.')
        else:
            self.stdout.write(self.style.WARNING('Stripe public key not set'))

        if client_secret:
            self.stdout.write('Stripe private key set.')
        else:
            self.stdout.write(self.style.WARNING('Stripe private key not set.'))

        if client_id and client_secret:
            try:
                import stripe
                stripe.api_key = getattr(settings,'STRIPE_PRIVATE_KEY','')
                stripe.Charge.list(limit=1)
            except ImportError:
                self.stdout.write(self.style.ERROR('Required Stripe API app ("stripe") not installed.'))
            except stripe.error.AuthenticationError:
                self.stdout.write(self.style.ERROR('Unauthorized credentials supplied for Stripe API.'))
            else:
                self.stdout.write(self.style.SUCCESS('Successfully connected to Stripe using API credentials.'))

        add_stripe_checkout = self.boolean_input('Add Stripe Checkout link to the registration summary view to allow students to pay [Y/n]', True)
        if add_stripe_checkout:
            home_page = Page.objects.filter(is_home=True,publisher_public=True).first()
            if not home_page:
                self.stdout.write(self.style.ERROR('Cannot add Stripe checkout link because a home page has not yet been set.'))
            else:
                stripe_sp = StaticPlaceholder.objects.get_or_create(code='registration_payment_placeholder')
                stripe_p_draft = stripe_sp[0].draft
                stripe_p_public = stripe_sp[0].public

                if stripe_p_public.get_plugins().filter(plugin_type='StripePaymentFormPlugin').exists():
                    self.stdout.write('Stripe Checkout button already present.')
                else:
                    add_plugin(
                        stripe_p_draft, 'StripePaymentFormPlugin', initial_language,
                        successPage=home_page,
                    )
                    add_plugin(
                        stripe_p_public, 'StripePaymentFormPlugin', initial_language,
                        successPage=home_page,
                    )
                    self.stdout.write('Stripe checkout link added.')
