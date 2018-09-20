from django.core.management.base import BaseCommand
from django.apps import apps
from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.sites.models import Site

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

        foundErrors = False

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
            foundErrors = True

        if client_id:
            self.stdout.write('Square application ID set.')
        else:
            self.stdout.write(self.style.WARNING('Square application ID not set'))
            foundErrors = True

        if client_secret:
            self.stdout.write('Square access token set.')
        else:
            self.stdout.write(self.style.WARNING('Square access token not set.'))
            foundErrors = True

        if location_id and client_id and client_secret:
            try:
                from squareconnect.rest import ApiException
                from squareconnect.apis.locations_api import LocationsApi
                from squareconnect.apis.transactions_api import TransactionsApi

                locations_api_instance = LocationsApi()
                locations_api_instance.api_client.configuration.access_token = getattr(settings,'SQUARE_ACCESS_TOKEN','')
                transactions_api_instance = TransactionsApi()
                transactions_api_instance.api_client.configuration.access_token = getattr(settings,'SQUARE_ACCESS_TOKEN','')

                # Check that the location ID from settings actually identifies a location.
                api_response = locations_api_instance.list_locations()
                if api_response.errors:
                    self.stdout.write(self.style.ERROR('Error in listing Locations: %s' % api_response.errors))
                    foundErrors = True
                if location_id not in [x.id for x in api_response.locations]:
                    self.stdout.write(self.style.ERROR('Location ID from settings does not identify a valid Square Location.'))
                    foundErrors = True

                # Check that we can access transaction information
                api_response = transactions_api_instance.list_transactions(location_id=location_id)
                if api_response.errors:
                    self.stdout.write(self.style.ERROR('Error in listing Transactions: %s' % api_response.errors))
                    foundErrors = True
                else:
                    self.stdout.write(self.style.SUCCESS('Successfully connected to Square API with provided credentials.'))
            except ImportError:
                self.stdout.write(self.style.ERROR('Required squareconnect app not installed.'))
                foundErrors = True
            except ApiException as e:
                self.stdout.write(self.style.ERROR('Exception in using Square API: %s\n' % e))
                foundErrors = True

        add_square_checkout = self.boolean_input('Add Square Checkout form to the registration summary view to allow students to pay [Y/n]', True)
        if add_square_checkout:
            home_page = Page.objects.filter(is_home=True,publisher_public=True).first()
            if not home_page:
                self.stdout.write(self.style.ERROR('Cannot add Square Checkout form because a home page has not yet been set.'))
                foundErrors = True
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
                    self.stdout.write(
                        """

Notes for Checkout integration
------------------------------

- In order for the Square checkout form to function on your
  website, you *must* be able to connect to the site using
  HTTPS, and the page on which your checkout form is included
  must be served over a secure connection via HTTPS.  Be sure
  that your server is set up to permit HTTPS connections, and that
  it automatically directs customers who are registering to
  an HTTPS connection.

- If you are running a development installation of the project
  on your local machine, then the above HTTPS requirement does
  not apply.  You will be able to see and test the checkout form
  on your local machine.

                        """
                    )

        add_square_pos = self.boolean_input('Add Square point-of-sale button to the registration summary view to allow students to pay [Y/n]', True)
        if add_square_pos:
            home_page = Page.objects.filter(is_home=True,publisher_public=True).first()
            if not home_page:
                self.stdout.write(self.style.ERROR('Cannot add Square point-of-sale button because a home page has not yet been set.'))
                foundErrors = True
            else:
                checkout_sp = StaticPlaceholder.objects.get_or_create(code='registration_payment_placeholder')
                checkout_p_draft = checkout_sp[0].draft
                checkout_p_public = checkout_sp[0].public

                if checkout_p_public.get_plugins().filter(plugin_type='SquarePointOfSalePlugin').exists():
                    self.stdout.write('Square point of sale button already present.')
                else:
                    add_plugin(
                        checkout_p_draft, 'SquarePointOfSalePlugin', initial_language,
                        successPage=home_page,
                    )
                    add_plugin(
                        checkout_p_public, 'SquarePointOfSalePlugin', initial_language,
                        successPage=home_page,
                    )
                    self.stdout.write('Square Checkout form added.')
                    self.stdout.write(
                        """

Notes for point-of-sale integration
-----------------------------------

- Before using the Square point of sale button, you must log in
  and specify the URL on this project to which Square sends
  notifications of each transaction.  This callback URL that you specify
  *must* be a secure HTTPS URL, which means that your server must permit
  HTTPS connections.  To register your callback URL, complete the following
  steps:

    1. Log into the Square website at https://squareup.com/, go to your
    dashboard, and under "Apps > My Apps" select "Manage App" for the
    app whose credentials you have specified for this project.
    2. Under the "Point of Sale API" tab, look for the input box labeled
    "Web Callback URLs."  In that input box, enter the following URL:

    https://%s%s

    3. Click "Save" at the bottom of the page to save your change.

- If you need to test Square point-of-sale integration on a local
  installation, you will need your local installation to be served
  over HTTPS.  Consider a solution such as django-sslserver
  (https://github.com/teddziuba/django-sslserver) for testing purposes.
  Also, be advised that you may need to configure settings on your
  router and/or your computer's firewall in order to ensure that your
  local machine can receive HTTPS callbacks from Square.

- Prior to using the Square point-of-sale button, you must also
  install the Square point-of-sale app on your Android or iOS
  device, and log in using the account whose credentials you have
  specified in the project settings.  If you attempt to begin a point
  of sale transaction without logging into this account, your transaction
  will fail with an error.

                        """ % (Site.objects.get_current().domain,reverse('processSquarePointOfSale'))
                    )
        if not foundErrors:
            self.stdout.write(self.style.SUCCESS('Square setup complete.'))
        else:
            self.stdout.write(self.style.ERROR('Square setup encountered errors.  Please see above for details.'))
