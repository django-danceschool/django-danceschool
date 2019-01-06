from django.core.management.base import BaseCommand
from django.apps import apps
from django.conf import settings

from six.moves import input

try:
    import readline
except ImportError:
    pass


class Command(BaseCommand):
    help = 'Create necessary placeholders for customers to elect to pay at the door.'

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
            ('danceschool.payments.payatdoor', 'At-the-door payments app'),
        ]
        for this_app in required_apps:
            if not apps.is_installed(this_app[0]):
                self.stdout.write(self.style.ERROR('ERROR: %s is not installed or listed in INSTALLED_APPS. Please install before proceeding.' % this_app[1]))
                return None

        self.stdout.write(
            """
CHECKING AT-THE-DOOR PAYMENTS INTEGRATION
-----------------------------------------
            """
        )

        add_payatdoor_checkout = self.boolean_input('Add At-the-door payments checkbox to the registration summary view to allow students to elect to pay at the door [Y/n]', True)
        if add_payatdoor_checkout:
            home_page = Page.objects.filter(is_home=True,publisher_is_draft=False).first()
            if not home_page:
                self.stdout.write(self.style.ERROR('Cannot add at-the-door payments checkbox because a home page has not yet been set.'))
            else:
                payment_sp = StaticPlaceholder.objects.get_or_create(code='registration_payment_placeholder')
                payment_p_draft = payment_sp[0].draft
                payment_p_public = payment_sp[0].public

                if payment_p_public.get_plugins().filter(plugin_type='PayAtDoorFormPlugin').exists():
                    self.stdout.write('At-the-door payments checkbox already present.')
                else:
                    add_plugin(
                        payment_p_draft, 'PayAtDoorFormPlugin', initial_language,
                        successPage=home_page,
                    )
                    add_plugin(
                        payment_p_public, 'PayAtDoorFormPlugin', initial_language,
                        successPage=home_page,
                    )
                    self.stdout.write('At-the-door payments checkbox added.')
