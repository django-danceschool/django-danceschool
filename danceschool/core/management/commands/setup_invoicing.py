from django.core.management.base import BaseCommand
from django.apps import apps

from danceschool.core.management.commands.setupschool import SetupMixin


class Command(SetupMixin, BaseCommand):
    help = 'Create necessary placeholders for staff members to generate and email invoices for registrations'

    def handle(self, *args, **options):

        from cms.api import add_plugin
 
        initial_language = self.get_setup_language()

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
            alias, alias_content = self.get_alias('registration_invoice_placeholder', initial_language)

            if alias..get_placeholder().get_plugins().filter(plugin_type='CreateInvoicePlugin').exists():
                self.stdout.write('Invoice generation form already present.')
            else:
                add_plugin(
                    alias_content.placeholder, 'CreateInvoicePlugin', initial_language,
                )
                self.stdout.write('Invoice generation form added.')
