'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.utils.translation import ugettext_lazy as _

from dynamic_preferences.types import BooleanPreference, IntegerPreference, Section
from dynamic_preferences.registries import global_preferences_registry

# we create some section objects to link related preferences together

privateLessons = Section('privateLessons', _('Private Lessons'))


############################
# Private Lessons Preferences
#
@global_preferences_registry.register
class AllowPublicBooking(BooleanPreference):
    section = privateLessons
    name = 'allowPublicBooking'
    verbose_name = _('Allow non-staff to book private lessons for themselves.')
    help_text = _('The private lesson booking functions will only be available to individuals with permissions unless this box is checked.')
    default = False


@global_preferences_registry.register
class AllowRegistration(BooleanPreference):
    section = privateLessons
    name = 'allowRegistration'
    verbose_name = _('Allow payment for private lessons through the registration system.')
    help_text = _('If the studio handles payment for private lessons, then checking this box allows users to process payment through the regular online registration system.  If the studio only handles booking for private lessons, but not payment, then this box should not be checked.')
    default = False


@global_preferences_registry.register
class OpenBookingDaysAhead(IntegerPreference):
    section = privateLessons
    name = 'openBookingDays'
    verbose_name = _('Open private lesson booking days in advance')
    help_text = _('If instructor availability has been configured, permitted users will be able to book private lessons beginning this many days in advance.  Enter 0 for no restiction.')
    default = 30


@global_preferences_registry.register
class CloseBookingDaysAhead(IntegerPreference):
    section = privateLessons
    name = 'closeBookingDays'
    verbose_name = _('Close private lesson booking days in advance')
    help_text = _('Enter 0 to allow booking up to the start time of the lesson.')
    default = 0


@global_preferences_registry.register
class DefaultLessonLength(IntegerPreference):
    section = privateLessons
    name = 'defaultLessonLength'
    verbose_name = _('Default lesson booking length (minutes)')
    default = 60


@global_preferences_registry.register
class LessonLengthInterval(IntegerPreference):
    section = privateLessons
    name = 'lessonLengthInterval'
    verbose_name = _('Interval in which lesson lengths can be changed (minutes)')
    default = 30


@global_preferences_registry.register
class MinimumLessonLength(IntegerPreference):
    section = privateLessons
    name = 'minimumLessonLength'
    verbose_name = _('Minimum lesson booking length (minutes)')
    help_text = _('Enter 0 for no limit')
    default = 30


@global_preferences_registry.register
class MaximumLessonLength(IntegerPreference):
    section = privateLessons
    name = 'maximumLessonLength'
    verbose_name = _('Maximum lesson booking length (minutes)')
    help_text = _('Enter 0 for no limit')
    default = 90
