'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.utils.translation import ugettext_lazy as _
from django.template.loader import get_template

from dynamic_preferences.types import BooleanPreference, IntegerPreference, ModelChoicePreference, Section
from dynamic_preferences.registries import global_preferences_registry

from danceschool.core.models import EventStaffCategory, EmailTemplate, get_defaultEmailName, get_defaultEmailFrom

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
    default = True


@global_preferences_registry.register
class AllowRegistration(BooleanPreference):
    section = privateLessons
    name = 'allowRegistration'
    verbose_name = _('Allow payment for private lessons through the registration system.')
    help_text = _('If the studio handles payment for private lessons, then checking this box allows users to process payment through the regular online registration system.  If the studio only handles booking for private lessons, but not payment, then this box should not be checked.')
    default = True


@global_preferences_registry.register
class NotifyPrivateLessonInstructor(BooleanPreference):
    section = privateLessons
    name = 'notifyInstructor'
    verbose_name = _('Notify instructor when a private lesson is booked')
    help_text = _('If checked, then instructors will receive a notification email whenever a private lesson is scheduled with them.')
    default = True


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


@global_preferences_registry.register
class StaffCategoryPrivateLesson(ModelChoicePreference):
    section = privateLessons
    name = 'eventStaffCategoryPrivateLesson'
    verbose_name = _('Private Lesson Event Staff Category')
    model = EventStaffCategory
    queryset = EventStaffCategory.objects.all()

    def get_default(self):
        return EventStaffCategory.objects.get_or_create(name=_('Private Lesson Instruction'))[0]


@global_preferences_registry.register
class LessonBookedEmailTemplate(ModelChoicePreference):
    section = privateLessons
    name = 'lessonBookedEmailTemplate'
    verbose_name = _('Email template used to notify customers that their lesson is scheduled')
    help_text = _('This email template will only be used for lesson bookings that do not go through the full online registration and payment system.')
    model = EmailTemplate
    queryset = EmailTemplate.objects.all()

    def get_default(self):

        initial_template = get_template('email/private_lesson_registration_success.html')
        with open(initial_template.origin.name,'r') as infile:
            content = infile.read()
            infile.close()

        return EmailTemplate.objects.get_or_create(
            name=_('Private Lesson Booking Confirmation Email'),
            defaults={
                'subject': _('Confirmation of Scheduled Private Lesson'),
                'content': content or '',
                'defaultFromAddress': get_defaultEmailFrom(),
                'defaultFromName': get_defaultEmailName(),
                'defaultCC': '',
                'hideFromForm': True,
            }
        )[0]


@global_preferences_registry.register
class LessonBookedInstructorEmailTemplate(ModelChoicePreference):
    section = privateLessons
    name = 'lessonBookedInstructorEmailTemplate'
    verbose_name = _('Email template used to notify instructors that a lesson has been scheduled')
    model = EmailTemplate
    queryset = EmailTemplate.objects.all()

    def get_default(self):

        initial_template = get_template('email/private_lesson_booking_alert.html')
        with open(initial_template.origin.name,'r') as infile:
            content = infile.read()
            infile.close()

        return EmailTemplate.objects.get_or_create(
            name=_('Private Lesson Booking Instructor Notification'),
            defaults={
                'subject': _('Notification of Private Lesson Scheduling'),
                'content': content or '',
                'defaultFromAddress': get_defaultEmailFrom(),
                'defaultFromName': get_defaultEmailName(),
                'defaultCC': '',
                'hideFromForm': True,
            }
        )[0]
