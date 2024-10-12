from django.core.management.base import BaseCommand
from django.apps import apps

from danceschool.core.management.commands.setupschool import SetupMixin

class Command(SetupMixin, BaseCommand):
    help = 'Create necessary placeholders for customers to elect to pay at the door.'

    def handle(self, *args, **options):

        from cms.api import add_plugin
        from cms.models import Page

        initial_language = self.get_setup_language()

        # Do some sanity checks to ensure that necessary apps are listed in INSTALLED_APPS
        # before proceeding
        required_apps = [
            ('cms', 'Django CMS'),
            ('danceschool.core', 'Core danceschool app'),
            ('danceschool.payments.payatdoor', 'At-the-door payments app'),
        ]
        for this_app in required_apps:
            if not apps.is_installed(this_app[0]):
                self.stdout.write(
                    self.style.ERROR(
                        ('ERROR: %s is not installed or listed ' % this_app[1]) +
                        'in INSTALLED_APPS. Please install before proceeding.'
                    )
                )
                return None

        self.stdout.write(
            """
CHECKING AT-THE-DOOR PAYMENTS INTEGRATION
-----------------------------------------
            """
        )

        add_payatdoor = self.boolean_input('Add form for staff members to record payments at the door [Y/n]', True)
        if add_payatdoor:
            alias, alias_content = self.get_alias('registration_payatdoor_placeholder', initial_language)

            if alias.cms_plugins.filter(plugin_type='PayAtDoorFormPlugin').exists():
                self.stdout.write('At-the-door payment processing form already present.')
            else:
                add_plugin(
                    alias_content.placeholder, 'PayAtDoorFormPlugin', initial_language,
                )
                self.stdout.write('At-the-door payment processing form added.')

            add_willpayatdoor = self.boolean_input(
                'Add At-the-door payments checkbox to the registration ' +
                'summary view to allow students to elect to pay at the door [Y/n]',
                True
            )
            if add_willpayatdoor:
                home_page = Page.objects.filter(is_home=True).first()
                if not home_page:
                    self.stdout.write(self.style.ERROR(
                        'Cannot add at-the-door payments checkbox because a ' +
                        'home page has not yet been set.'
                    ))
                else:
                    alias, alias_content = self.get_alias('registration_payment_placeholder', initial_language)

                    if alias.cms_plugins.filter(plugin_type='WillPayAtDoorFormPlugin').exists():
                        self.stdout.write('At-the-door payments checkbox already present.')
                    else:
                        add_plugin(
                            alias_content.placeholder, 'WillPayAtDoorFormPlugin', initial_language,
                            successPage=home_page,
                        )
                        self.stdout.write('At-the-door payments checkbox added.')
