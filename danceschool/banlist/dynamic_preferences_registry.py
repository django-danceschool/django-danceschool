from django.utils.translation import ugettext_lazy as _

from dynamic_preferences.types import BooleanPreference, StringPreference, Section
from dynamic_preferences.registries import global_preferences_registry

# we create some section objects to link related preferences together

registration = Section('registration', _('Registration'))


@global_preferences_registry.register
class BanListEnabled(BooleanPreference):
    section = registration
    name = 'enableBanList'
    verbose_name = _('Enable Automated Enforcement of Ban List')
    help_text = _(
        'If this box is checked, then if an individual whose name or email ' +
        'address appears on the ban list will be prevented from registration ' +
        'and asked to contact the school.  Their attempt to register will be logged.'
    )
    default = True


@global_preferences_registry.register
class BanListContactEmail(StringPreference):
    section = registration
    name = 'banListContactEmail'
    verbose_name = _(
        'Individuals who are prevented from registration are asked ' +
        'to contact this address.'
    )
    help_text = _('If no email is specified, then the default school email will be used.')
    default = ''


@global_preferences_registry.register
class BanListNotificationEmail(StringPreference):
    section = registration
    name = 'banListNotificationEmail'
    verbose_name = _(
        'Send a notification of attempted registration by banned users to ' +
        'this address (optional).'
    )
    help_text = _('If no email is specified, then no notification will be sent.')
    default = ''
