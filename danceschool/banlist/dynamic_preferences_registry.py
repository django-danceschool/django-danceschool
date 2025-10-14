from django.utils.translation import gettext_lazy as _

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
    required = False


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
    required = False


@global_preferences_registry.register
class BanListNotificationText(StringPreference):
    section = registration
    name = 'banListNotificationText'
    verbose_name = _(
        'Show the following text to banned users who attempt to register online.'
    )
    default = (
        'There appears to be an issue with this registration. '
        'Please contact {respondTo} to proceed with the registration process. '
        'You may reference the error code {flagCode}.'
    )
    required = False


@global_preferences_registry.register
class BanListDoorNotificationText(StringPreference):
    section = registration
    name = 'banListDoorNotificationText'
    verbose_name = _(
        'Show the following text when banned users attempt to register at the door.'
    )
    default = (
        'This person currently prevented from registration because they are on '
        'the banned users list. This registration attempt has been flagged and '
        'recorded using error code {flagCode}.'
    )
    required = False
