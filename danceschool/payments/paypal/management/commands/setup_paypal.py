from django.core.management.base import BaseCommand
from django.apps import apps
from django.conf import settings

from six.moves import input

try:
    import readline
except ImportError:
    pass


class Command(BaseCommand):
    help = 'Check Paypal settings and created necessary placeholders for Paypal Express Checkout integration.'

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
            ('danceschool.payments.paypal', 'Paypal integration app'),
            ('dynamic_preferences', 'django-dynamic-preferences'),
        ]
        for this_app in required_apps:
            if not apps.is_installed(this_app[0]):
                self.stdout.write(self.style.ERROR('ERROR: %s is not installed or listed in INSTALLED_APPS. Please install before proceeding.' % this_app[1]))
                return None

        self.stdout.write(
            """
CHECKING PAYPAL INTEGRATION
---------------------------
            """
        )

        mode = getattr(settings,'PAYPAL_MODE',None)
        client_id = getattr(settings,'PAYPAL_CLIENT_ID','')
        client_secret = getattr(settings,'PAYPAL_CLIENT_SECRET','')

        if mode in ['sandbox','live']:
            self.stdout.write('Paypal Mode: %s, OK' % mode)
        else:
            self.stdout.write(self.style.WARNING('Paypal Mode: not set'))

        if client_id:
            self.stdout.write('Paypal client ID set.')
        else:
            self.stdout.write(self.style.WARNING('Paypal client ID not set'))

        if client_secret:
            self.stdout.write('Paypal client secret set.')
        else:
            self.stdout.write(self.style.WARNING('Paypal client secret not set.'))

        if mode in ['sandbox','live'] and client_id and client_secret:
            try:
                import paypalrestsdk
                paypalrestsdk.configure({
                    'mode': mode or 'sandbox',
                    'client_id': client_id,
                    'client_secret': client_secret,
                })
                paypalrestsdk.Payment.all({'count': 1})
            except ImportError:
                self.stdout.write(self.style.ERROR('Required paypalrestsdk app not installed.'))
            except paypalrestsdk.exceptions.UnauthorizedAccess:
                self.stdout.write(self.style.ERROR('Unauthorized credentials supplied for Paypal API.'))
            else:
                self.stdout.write(self.style.SUCCESS('Successfully connected to Paypal using API credentials.'))

        add_paypal_paynow = self.boolean_input('Add Paypal Pay Now link to the registration summary view to allow students to pay [Y/n]', True)
        if add_paypal_paynow:
            home_page = Page.objects.filter(is_home=True,publisher_public=True).first()
            if not home_page:
                self.stdout.write(self.style.ERROR('Cannot add Pay Now link because a home page has not yet been set.'))
            else:
                paynow_sp = StaticPlaceholder.objects.get_or_create(code='registration_payment_placeholder')
                paynow_p_draft = paynow_sp[0].draft
                paynow_p_public = paynow_sp[0].public

                if paynow_p_public.get_plugins().filter(plugin_type='CartPaymentFormPlugin').exists():
                    self.stdout.write('Paypal Pay Now button already present.')
                else:
                    add_plugin(
                        paynow_p_draft, 'CartPaymentFormPlugin', initial_language,
                        successPage=home_page,
                    )
                    add_plugin(
                        paynow_p_public, 'CartPaymentFormPlugin', initial_language,
                        successPage=home_page,
                    )
                    self.stdout.write('Paypal Pay Now link added.')
