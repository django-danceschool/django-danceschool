from django.core.management.base import BaseCommand
from django.apps import apps
from django.conf import settings

from six.moves import input

try:
    import readline
except ImportError:
    pass


class Command(BaseCommand):
    help = 'Check Square settings and create necessary placeholders for Square Checkout integration.'

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
            ('danceschool.payments.square', 'Square integration app'),
        ]
        for this_app in required_apps:
            if not apps.is_installed(this_app[0]):
                self.stdout.write(self.style.ERROR('ERROR: %s is not installed or listed in INSTALLED_APPS. Please install before proceeding.' % this_app[1]))
                return None

        self.stdout.write(
            """
CHECKING SQUARE INTEGRATION
---------------------------
            """
        )

        location_id = getattr(settings,'SQUARE_LOCATION_ID','')
        client_id = getattr(settings,'SQUARE_APPLICATION_ID','')
        client_secret = getattr(settings,'SQUARE_ACCESS_TOKEN','')

        if location_id:
            self.stdout.write('Square location ID set.')
        else:
            self.stdout.write(self.style.WARNING('Square location ID not set'))

        if client_id:
            self.stdout.write('Square application ID set.')
        else:
            self.stdout.write(self.style.WARNING('Square application ID not set'))

        if client_secret:
            self.stdout.write('Square access token set.')
        else:
            self.stdout.write(self.style.WARNING('Square access token not set.'))

        if location_id and client_id and client_secret:
            try:
                import squareconnect
                from squareconnect.rest import ApiException
                from squareconnect.apis.locations_api import LocationsApi
                from squareconnect.apis.transactions_api import TransactionsApi

                squareconnect.configuration.access_token = client_secret
                locations_api_instance = LocationsApi()
                transactions_api_instance = TransactionsApi()

                # Check that the location ID from settings actually identifies a location.
                api_response = locations_api_instance.list_locations()
                if api_response.errors:
                    self.stdout.write(self.style.ERROR('Error in listing Locations: %s' % api_response.errors))
                if location_id not in [x.id for x in api_response.locations]:
                    self.stdout.write(self.style.ERROR('Location ID from settings does not identify a valid Square Location.'))

                # Check that we can access transaction information
                api_response = transactions_api_instance.list_transactions(location_id=location_id)
                if api_response.errors:
                    self.stdout.write(self.style.ERROR('Error in listing Transactions: %s' % api_response.errors))
                else:
                    self.stdout.write(self.style.SUCCESS('Successfully connected to Square API with provided credentials.'))
            except ImportError:
                self.stdout.write(self.style.ERROR('Required squareconnect app not installed.'))
            except ApiException as e:
                self.stdout.write(self.style.ERROR('Exception in using Square API: %s\n' % e))

        add_square_checkout = self.boolean_input('Add Square Checkout form to the registration summary view to allow students to pay [Y/n]', True)
        if add_square_checkout:
            home_page = Page.objects.filter(is_home=True,publisher_public=True).first()
            if not home_page:
                self.stdout.write(self.style.ERROR('Cannot add Square Checkout form because a home page has not yet been set.'))
            else:
                checkout_sp = StaticPlaceholder.objects.get_or_create(code='registration_payment_placeholder')
                checkout_p_draft = checkout_sp[0].draft
                checkout_p_public = checkout_sp[0].public

                if checkout_p_public.get_plugins().filter(plugin_type='SquareCheckoutFormPlugin').exists():
                    self.stdout.write('Square checkout form already present.')
                else:
                    add_plugin(
                        checkout_p_draft, 'SquareCheckoutFormPlugin', initial_language,
                        successPage=home_page,
                    )
                    add_plugin(
                        checkout_p_public, 'SquareCheckoutFormPlugin', initial_language,
                        successPage=home_page,
                    )
                    self.stdout.write('Square Checkout form added.')
