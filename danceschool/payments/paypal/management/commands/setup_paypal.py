from django.core.management.base import BaseCommand
from django.apps import apps
from django.conf import settings

from danceschool.core.management.commands.setupschool import SetupMixin


class Command(SetupMixin, BaseCommand):
    help = 'Check Paypal settings and created necessary placeholders for Paypal Express Checkout integration.'

    def handle(self, *args, **options):

        from cms.api import add_plugin
        from cms.models import Page

        initial_language = self.get_setup_language()

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
                self.stdout.write(self.style.ERROR(
                    ('ERROR: %s is not installed or listed in ' % this_app[1]) +
                    'INSTALLED_APPS. Please install before proceeding.'
                ))
                return None

        self.stdout.write(
            """
CHECKING PAYPAL INTEGRATION
---------------------------
            """
        )

        mode = getattr(settings, 'PAYPAL_MODE', None)
        client_id = getattr(settings, 'PAYPAL_CLIENT_ID', '')
        client_secret = getattr(settings, 'PAYPAL_CLIENT_SECRET', '')

        if mode in ['sandbox', 'live']:
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

        if mode in ['sandbox', 'live'] and client_id and client_secret:
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

        add_paypal_paynow = self.boolean_input(
            'Add Paypal Pay Now link to the registration summary view to ' +
            'allow students to pay [Y/n]', True
        )
        if add_paypal_paynow:
            home_page = Page.objects.filter(is_home=True).first()
            if not home_page:
                self.stdout.write(self.style.ERROR('Cannot add Pay Now link because a home page has not yet been set.'))
            else:
                placeholders = [
                    ('registration_payment_placeholder', 'online registrations'),
                    ('registration_payatdoor_placeholder', 'at-the-door payments')
                ]

                for p in placeholders:
                    alias, alias_content = self.get_alias(p[0], initial_language)

                    if alias.get_placeholder().get_plugins().filter(plugin_type='CartPaymentFormPlugin').exists():
                        self.stdout.write('Paypal Pay Now button already present for %s.' % p[1])
                    else:
                        add_plugin(
                            alias_content.placeholder, 'CartPaymentFormPlugin', initial_language,
                            successPage=home_page,
                        )
                        self.stdout.write('Paypal Pay Now link added for %s.' % p[1])
