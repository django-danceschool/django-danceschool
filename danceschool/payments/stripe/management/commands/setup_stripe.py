from django.core.management.base import BaseCommand
from django.apps import apps
from django.conf import settings

from danceschool.core.management.commands.setupschool import SetupMixin


class Command(SetupMixin, BaseCommand):
    help = (
        'Check Stripe settings and created necessary placeholders ' +
        'for Stripe Checkout integration.'
    )

    def handle(self, *args, **options):

        from cms.api import add_plugin
        from cms.models import Page

        initial_language = self.get_setup_language()

        # Do some sanity checks to ensure that necessary apps are listed in INSTALLED_APPS
        # before proceeding
        required_apps = [
            ('cms', 'Django CMS'),
            ('danceschool.core', 'Core danceschool app'),
            ('danceschool.payments.stripe', 'Stripe integration app'),
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
CHECKING STRIPE INTEGRATION
---------------------------
            """
        )

        client_id = getattr(settings, 'STRIPE_PUBLIC_KEY', '')
        client_secret = getattr(settings, 'STRIPE_PRIVATE_KEY', '')

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
                stripe.api_key = getattr(settings, 'STRIPE_PRIVATE_KEY', '')
                stripe.Charge.list(limit=1)
            except ImportError:
                self.stdout.write(self.style.ERROR('Required Stripe API app ("stripe") not installed.'))
            except stripe.error.AuthenticationError:
                self.stdout.write(self.style.ERROR('Unauthorized credentials supplied for Stripe API.'))
            else:
                self.stdout.write(self.style.SUCCESS('Successfully connected to Stripe using API credentials.'))

        add_stripe_checkout = self.boolean_input(
            'Add Stripe Checkout link to the registration summary view to ' +
            'allow students to pay [Y/n]', True
        )
        if add_stripe_checkout:
            home_page = Page.objects.filter(is_home=True).first()
            if not home_page:
                self.stdout.write(self.style.ERROR(
                    'Cannot add Stripe checkout link because a home page has ' +
                    'not yet been set.'
                ))
            else:
                placeholders = [
                    ('registration_payment_placeholder', 'online registrations'),
                    ('registration_payatdoor_placeholder', 'at-the-door payments')
                ]

                for p in placeholders:
                    alias, alias_content = self.get_alias(p[0], initial_language)

                    if alias.get_placeholder().get_plugins().filter(plugin_type='StripePaymentFormPlugin').exists():
                        self.stdout.write('Stripe Checkout button already present for %s.' % p[1])
                    else:
                        add_plugin(
                            alias_content.placeholder, 'StripePaymentFormPlugin', initial_language,
                            successPage=home_page,
                        )
                        self.stdout.write('Stripe checkout link added for %s.' % p[1])
