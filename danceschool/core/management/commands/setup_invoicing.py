from django.core.management.base import BaseCommand
from django.apps import apps
from django.conf import settings

from six.moves import input

try:
    import readline
except ImportError:
    pass


class Command(BaseCommand):
    help = 'Create necessary placeholders for staff members to generate and email invoices for registrations'

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
        ]
        for this_app in required_apps:
            if not apps.is_installed(this_app[0]):
                self.stdout.write(
                    self.style.ERROR(
                        'ERROR: %s is not installed or listed in INSTALLED_APPS. Please install before proceeding.' % (
                            this_app[1],
                        )
                    )
                )
                return None

        self.stdout.write(
            """
CHECKING INVOICE GENERATION FUNCTIONALITY
-----------------------------------------
            """
        )

        add_invoicing = self.boolean_input(
            'Add invoice generation plugin to the registration summary view to ' +
            'allow staff members to generate and email invoices for registrations [Y/n]',
            True
        )
        if add_invoicing:
            invoice_sp = StaticPlaceholder.objects.get_or_create(code='registration_invoice_placeholder')
            invoice_p_draft = invoice_sp[0].draft
            invoice_p_public = invoice_sp[0].public

            if invoice_p_public.get_plugins().filter(plugin_type='CreateInvoicePlugin').exists():
                self.stdout.write('Invoice generation form already present.')
            else:
                add_plugin(
                    invoice_p_draft, 'CreateInvoicePlugin', initial_language,
                )
                add_plugin(
                    invoice_p_public, 'CreateInvoicePlugin', initial_language,
                )
                self.stdout.write('Invoice generation form added.')
