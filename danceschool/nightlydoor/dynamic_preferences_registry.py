'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.utils.translation import ugettext_lazy as _

from dynamic_preferences.types import BooleanPreference, ChoicePreference, Section
from dynamic_preferences.registries import global_preferences_registry


# Generate a backup section in global preferences.
nightlydoor = Section('nightlydoor', _('Nightly Door'))


@global_preferences_registry.register
class RequireFullRegistration(ChoicePreference):
    section = nightlydoor
    name = 'requireFullRegistration'
    choices = [
        ('Always', _('Always')),
        ('SeriesOnly', _('For class series but not for events')),
        ('EventsOnly', _('For events but not for class series')),
        ('Never', _('Never')),
    ]
    verbose_name = _('Require name and email with registration')
    default = 'Always'


@global_preferences_registry.register
class EnableVoucherEntry(BooleanPreference):
    section = nightlydoor
    name = 'enableVoucherEntry'
    verbose_name = _('Enable entry of voucher codes on register page')
    default = False
    help_text = _(
        'If this option is enabled, then a box will show up to permit entry of voucher codes ' +
        'on the register page. This is useful when full registration is not required, otherwise ' +
        'the voucher code box on the student info page may be used.'
    )


@global_preferences_registry.register
class AllowStudentRegistration(ChoicePreference):
    section = nightlydoor
    name = 'allowStudentReg'
    verbose_name = _('Enable registration with student discount')
    choices = [
        ('Always', _('Always')),
        ('SeriesOnly', _('For class series but not for events')),
        ('EventsOnly', _('For events but not for class series')),
        ('Never', _('Never')),
    ]
    default = 'Never'
    help_text = _(
        'If this option is enabled, then each applicable series or event on the register ' +
        'page will have buttons to register with a student discount.'
    )


@global_preferences_registry.register
class AllowCompedRegistration(ChoicePreference):
    section = nightlydoor
    name = 'allowCompedReg'
    verbose_name = _('Enable comped/free registration')
    choices = [
        ('Always', _('Always')),
        ('SeriesOnly', _('For class series but not for events')),
        ('EventsOnly', _('For events but not for class series')),
        ('Never', _('Never')),
    ]
    default = 'Never'
    help_text = _(
        'If this option is enabled, then each applicable series or event on the register ' +
        'page will have buttons to register for free in \'additional options.\' This is ' +
        'useful for purposes of accounting for registrations.'
    )
