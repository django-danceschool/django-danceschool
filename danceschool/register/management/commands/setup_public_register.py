from django.core.management.base import BaseCommand
from django.apps import apps

from danceschool.core.management.commands.setupschool import SetupMixin


class Command(SetupMixin, BaseCommand):
    help = (
        'Create the public_register_content alias and populate it with the '
        'default three-section layout (open series, open public events, '
        'closed/ongoing series).'
    )

    def handle(self, *args, **options):

        from cms.api import add_plugin

        required_apps = [
            ('cms', 'Django CMS'),
            ('danceschool.core', 'Core danceschool app'),
            ('danceschool.register', 'Register app'),
        ]
        for this_app in required_apps:
            if not apps.is_installed(this_app[0]):
                self.stdout.write(self.style.ERROR(
                    'ERROR: %s is not installed or listed in INSTALLED_APPS. '
                    'Please install before proceeding.' % this_app[1]
                ))
                return None

        self.stdout.write(
            """
PUBLIC REGISTRATION PAGE
------------------------
            """
        )

        add_public_register = self.boolean_input(
            'Set up the public registration alias with a default navigation '
            'bar and event listing plugins [Y/n]',
            True
        )
        if not add_public_register:
            return

        initial_language = self.get_setup_language()
        alias, alias_content = self.get_alias('public_register_content', initial_language)

        if alias.cms_plugins.all():
            self.stdout.write('Public registration content already populated, skipping.')
            return

        placeholder = alias_content.placeholder

        add_plugin(placeholder, 'PublicRegisterNavPlugin', initial_language)
        self.stdout.write('Navigation bar plugin added.')

        # Section 1: class series open for registration
        add_plugin(
            placeholder, 'PublicRegisterEventPlugin', initial_language,
            title='Upcoming Classes',
            eventType='S',
            registrationOpenLimit='O',
            occursWithinDays=None,
        )
        self.stdout.write('Upcoming classes plugin added.')

        # Section 2: public events open for registration
        add_plugin(
            placeholder, 'PublicRegisterEventPlugin', initial_language,
            title='Upcoming Events',
            eventType='P',
            registrationOpenLimit='O',
            occursWithinDays=None,
        )
        self.stdout.write('Upcoming events plugin added.')

        # Section 3: ongoing series closed for registration.
        # daysStart=0 → endTime__gte=now (exclude already-ended series).
        # daysEnd=0   → startTime__lte=now (exclude not-yet-started series).
        add_plugin(
            placeholder, 'PublicRegisterEventPlugin', initial_language,
            title='Ongoing Classes',
            eventType='S',
            registrationOpenLimit='C',
            occursWithinDays=None,
            daysStart=0,
            daysEnd=0,
        )
        self.stdout.write('Ongoing classes plugin added.')

        self.stdout.write(self.style.SUCCESS(
            'Public registration content alias set up successfully.'
        ))
