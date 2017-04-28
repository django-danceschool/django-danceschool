'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.forms import HiddenInput
from django.utils.translation import ugettext_lazy as _

from dynamic_preferences.types import BooleanPreference, StringPreference, IntegerPreference, ModelChoicePreference, Section
from dynamic_preferences.registries import global_preferences_registry
from filer.models import Folder
from cms.models import Page
from cms.forms.fields import PageSelectFormField

from .utils.serializers import PageModelSerializer

# we create some section objects to link related preferences together

general = Section('general', _('General Settings'))
contact = Section('contact', _('Contact Info'))
registration = Section('registration', _('Registration'))
email = Section('email', _('Email'))
calendar = Section('calendar', _('Calendar'))


############################
# General Preferences
#
@global_preferences_registry.register
class CurrencyCode(StringPreference):
    section = general
    name = 'currencyCode'
    verbose_name = _('Currency Code')
    help_text = _('Use a three-letter currency code for compatibility with payment systems')
    default = 'USD'


@global_preferences_registry.register
class CurrencySymbol(StringPreference):
    section = general
    name = 'currencySymbol'
    verbose_name = _('Currency Symbol')
    help_text = _('Enter a symbol to use on the website representing the currency used (e.g. $)')
    default = '$'


@global_preferences_registry.register
class StaffPhotosFolder(ModelChoicePreference):
    section = general
    model = Folder
    queryset = Folder.objects.all()
    name = 'staffPhotosFolder'
    verbose_name = _('Staff Photos Folder')
    help_text = _(
        'The folder used to store profile photos of staff members. ' +
        'Note that if this is changed, existing profile photos linked to staff members will not be moved.')
    default = Folder.objects.none()


@global_preferences_registry.register
class DefaultAdminSuccessPage(IntegerPreference):
    section = general
    model = Page
    name = 'defaultAdminSuccessPage'
    verbose_name = _('Default Admin Form Success Page')
    help_text = _('The page to which a staff user is redirected after successfully submitting an admin form.')
    default = Page.objects.none()
    field_class = PageSelectFormField

    def __init__(self, *args, **kwargs):
        ''' Changes the default serializer '''
        super(self.__class__, self).__init__(*args, **kwargs)
        self.serializer = PageModelSerializer


@global_preferences_registry.register
class RoleLead(IntegerPreference):
    section = general
    name = 'roleLeadID'
    widget = HiddenInput
    verbose_name = _('ID of automatically-generated Lead DanceRole')

    # Default is treated as undefined, but it should be set by apps.py when the site is initialized
    default = 0


@global_preferences_registry.register
class RoleFollow(IntegerPreference):
    section = general
    name = 'roleFollowID'
    widget = HiddenInput
    verbose_name = _('ID of automatically-generated Follow DanceRole')

    # Default is treated as undefined, but it should be set by apps.py when the site is initialized
    default = 0


@global_preferences_registry.register
class StaffCategoryInstructor(IntegerPreference):
    section = general
    name = 'eventStaffCategoryInstructorID'
    widget = HiddenInput
    verbose_name = _('ID of automatically-generated Instructor EventStaffCategory')

    # Default is treated as undefined, but it should be set by apps.py when the site is initialized
    default = 0


@global_preferences_registry.register
class StaffCategoryAssistant(IntegerPreference):
    section = general
    name = 'eventStaffCategoryAssistantID'
    widget = HiddenInput
    verbose_name = _('ID of automatically-generated Assistant Instructor EventStaffCategory')

    # Default is treated as undefined, but it should be set by apps.py when the site is initialized
    default = 0


@global_preferences_registry.register
class StaffCategorySubstitute(IntegerPreference):
    section = general
    name = 'eventStaffCategorySubstituteID'
    widget = HiddenInput
    verbose_name = _('ID of automatically-generated Substitute Teacher EventStaffCategory')

    # Default is treated as undefined, but it should be set by apps.py when the site is initialized
    default = 0


@global_preferences_registry.register
class StaffCategoryOther(IntegerPreference):
    section = general
    name = 'eventStaffCategoryOtherID'
    widget = HiddenInput
    verbose_name = _('ID of automatically-generated Other Staff EventStaffCategory')

    # Default is treated as undefined, but it should be set by apps.py when the site is initialized
    default = 0


#################################
# Contact Information Preferences
#
@global_preferences_registry.register
class BusinessName(StringPreference):
    section = contact
    name = 'businessName'
    verbose_name = _('Business Name')
    help_text = _('For invoices and template use')
    default = ''


@global_preferences_registry.register
class BusinessPhone(StringPreference):
    section = contact
    name = 'businessPhone'
    verbose_name = _('Business phone number')
    default = ''

    def get_field_kwargs(self):
        field_kwargs = super(self.__class__,self).get_field_kwargs()
        field_kwargs['required'] = False
        return field_kwargs


@global_preferences_registry.register
class BusinessEmail(StringPreference):
    section = contact
    name = 'businessEmail'
    verbose_name = _('Business email address')
    help_text = 'For invoices and template use'
    default = ''


@global_preferences_registry.register
class BusinessAddress(StringPreference):
    section = contact
    name = 'businessAddress'
    verbose_name = _('Business street/mailing address (Line 1)')
    default = ''

    def get_field_kwargs(self):
        field_kwargs = super(self.__class__,self).get_field_kwargs()
        field_kwargs['required'] = False
        return field_kwargs


@global_preferences_registry.register
class BusinessAddressLineTwo(StringPreference):
    section = contact
    name = 'businessAddressLineTwo'
    verbose_name = _('Business Address Line 2')
    help_text = 'Optional'
    default = ''

    def get_field_kwargs(self):
        field_kwargs = super(self.__class__,self).get_field_kwargs()
        field_kwargs['required'] = False
        return field_kwargs


@global_preferences_registry.register
class BusinessCity(StringPreference):
    section = contact
    name = 'businessCity'
    verbose_name = _('City')
    default = ''

    def get_field_kwargs(self):
        field_kwargs = super(self.__class__,self).get_field_kwargs()
        field_kwargs['required'] = False
        return field_kwargs


@global_preferences_registry.register
class BusinessState(StringPreference):
    section = contact
    name = 'businessState'
    verbose_name = _('State')
    default = ''

    def get_field_kwargs(self):
        field_kwargs = super(self.__class__,self).get_field_kwargs()
        field_kwargs['required'] = False
        return field_kwargs


@global_preferences_registry.register
class BusinessZip(StringPreference):
    section = contact
    name = 'businessZip'
    verbose_name = _('ZIP/Postal Code')
    default = ''

    def get_field_kwargs(self):
        field_kwargs = super(self.__class__,self).get_field_kwargs()
        field_kwargs['required'] = False
        return field_kwargs


@global_preferences_registry.register
class BusinessCountryCode(StringPreference):
    section = contact
    name = 'businessCountryCode'
    verbose_name = _('Country code')
    help_text = _('Use a two-letter country code for compatibility with payment systems')
    default = 'US'


#################################
# Registration-Related Preferences
#
@global_preferences_registry.register
class EnableRegistration(BooleanPreference):
    section = registration
    name = 'registrationEnabled'
    verbose_name = _('Registration Enabled')
    help_text = _('Uncheck this to disable registration entirely.  Useful when performing upgrades or testing.')
    default = True


@global_preferences_registry.register
class DefaultClassCapacity(IntegerPreference):
    section = registration
    name = 'defaultEventCapacity'
    verbose_name = _('Default Registration Capacity')
    help_text = _('This is usually a location-specific setting or an event-specific setting.  However, if a limit is not otherwise provided, then this will limit the number of registrations allowed.')
    default = 50


@global_preferences_registry.register
class RegistrationClosesAfterDays(IntegerPreference):
    section = registration
    name = 'closeAfterDays'
    verbose_name = _('Close Registration Days After Beginning')
    help_text = _('By default, online registration closes automatically this many days from the beginning of an Event or Series (e.g. Enter 2 to close two days after beginning, or enter -3 to close three days before beginning).  This value can be overridden for individual Events.')
    default = 7


@global_preferences_registry.register
class AllowAjaxSignin(BooleanPreference):
    section = registration
    name = 'allowAjaxSignin'
    verbose_name = _('Allow users to login/signup during registration')
    help_text = _('If you don\'t allow customers to see their history or do automatic checks for prerequisites, then you may not need customers to create user accounts or authenticate themselves. If this box is unchecked, then users will not be able to log in or create a new account during the registration process.')
    default = True


@global_preferences_registry.register
class DoorRegistrationSuccessPage(IntegerPreference):
    section = registration
    model = Page
    name = 'doorRegistrationSuccessPage'
    verbose_name = _('Door Registration Form Success Page')
    help_text = _('The page to which a staff user is redirected after successfully submitting an at-the-door registration.')
    default = Page.objects.none()
    field_class = PageSelectFormField

    def __init__(self, *args, **kwargs):
        ''' Changes the default serializer '''
        super(self.__class__, self).__init__(*args, **kwargs)
        self.serializer = PageModelSerializer


############################
# Email Preferences
#
@global_preferences_registry.register
class SiteEmailsDisabled(BooleanPreference):
    section = email
    name = 'disableSiteEmails'
    verbose_name = _('Disable Sending of Emails')
    help_text = _('Check to disable all standard emails from being sent.')
    default = False


@global_preferences_registry.register
class DefaultEmailsFrom(StringPreference):
    section = email
    name = 'defaultEmailFrom'
    verbose_name = _('Email address that general site emails are sent from')
    help_text = _('This email address may be overridden by specific email templates')
    default = ''

    def get_field_kwargs(self):
        field_kwargs = super(self.__class__,self).get_field_kwargs()
        field_kwargs['required'] = False
        return field_kwargs


@global_preferences_registry.register
class DefaultEmailsName(StringPreference):
    section = email
    name = 'defaultEmailName'
    verbose_name = _('Name that is used for general site emails')
    help_text = _('This name may be overridden by specific email templates')
    default = ''

    def get_field_kwargs(self):
        field_kwargs = super(self.__class__,self).get_field_kwargs()
        field_kwargs['required'] = False
        return field_kwargs


@global_preferences_registry.register
class ErrorEmailsEnabled(BooleanPreference):
    section = email
    name = 'enableErrorEmails'
    verbose_name = _('Send Error Emails')
    default = True


@global_preferences_registry.register
class ErrorEmailsFrom(StringPreference):
    section = email
    name = 'errorEmailFrom'
    verbose_name = _('Email address that error emails are sent from')
    default = ''

    def get_field_kwargs(self):
        field_kwargs = super(self.__class__,self).get_field_kwargs()
        field_kwargs['required'] = False
        return field_kwargs


@global_preferences_registry.register
class ErrorEmailsTo(StringPreference):
    section = email
    name = 'errorEmailTo'
    verbose_name = _('Email address that error emails are sent to')
    default = ''

    def get_field_kwargs(self):
        field_kwargs = super(self.__class__,self).get_field_kwargs()
        field_kwargs['required'] = False
        return field_kwargs


@global_preferences_registry.register
class RegSuccessEmailTemplate(IntegerPreference):
    section = email
    name = 'registrationSuccessTemplateID'
    widget = HiddenInput
    verbose_name = _('ID of template used for successful email registrations')

    # Default is treated as undefined, but it should be set by apps.py when the site is initialized
    default = 0


@global_preferences_registry.register
class InvoiceEmailTemplate(IntegerPreference):
    section = email
    name = 'invoiceTemplateID'
    widget = HiddenInput
    verbose_name = _('ID of template used for invoice creation')

    # Default is treated as undefined, but it should be set by apps.py when the site is initialized
    default = 0


############################
# Calendar Preferences
#
@global_preferences_registry.register
class EnableCalendarFeed(BooleanPreference):
    section = calendar
    name = 'calendarFeedEnabled'
    verbose_name = _('Enable public calendar feed')
    help_text = _('Uncheck to disable the automatic creation of a public calendar feed.')
    default = True


@global_preferences_registry.register
class EnablePrivateCalendarFeed(BooleanPreference):
    section = calendar
    name = 'privateCalendarFeedEnabled'
    verbose_name = _('Enable private calendar feed')
    help_text = _('Uncheck to disable the automatic creation of private (per-instructor) calendar feeds.')
    default = True


@global_preferences_registry.register
class CalendarClassColor(StringPreference):
    section = calendar
    name = 'defaultClassColor'
    verbose_name = _('Default color used for classes on the calendar')
    help_text = _('Enter a CSS compatible color')
    default = '#477087'


@global_preferences_registry.register
class CalendarEventColor(StringPreference):
    section = calendar
    name = 'defaultEventColor'
    verbose_name = _('Default color used for events on the calendar')
    help_text = _('Enter a CSS compatible color')
    default = '#477087'
