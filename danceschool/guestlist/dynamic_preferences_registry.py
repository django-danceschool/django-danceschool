'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.utils.translation import gettext_lazy as _

from dynamic_preferences.types import BooleanPreference, Section
from dynamic_preferences.registries import global_preferences_registry

# we create some section objects to link related preferences together
registration = Section('registration', _('Registration'))


@global_preferences_registry.register
class AddGuestListToViewRegistrations(BooleanPreference):
    section = registration
    name = 'addGuestListToViewRegistrations'
    verbose_name = _('Add guest list names when viewing registrations')
    help_text = _(
        'Check this box if you want guest list members to show us as ' +
        '"Additional Guests" on the View Registrations page for quicker ' +
        'check-in to events.'
    )
    default = False
