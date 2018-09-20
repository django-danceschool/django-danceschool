'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.utils.translation import ugettext_lazy as _
from django.template.loader import get_template

from dynamic_preferences.types import BooleanPreference, StringPreference, IntegerPreference, FloatPreference, ChoicePreference, ModelChoicePreference, Section
from dynamic_preferences.registries import global_preferences_registry
from filer.models import Folder
from cms.models import Page
from cms.forms.fields import PageSelectFormField

from .utils.serializers import PageModelSerializer
from .models import EventStaffCategory, EmailTemplate, get_defaultEmailName, get_defaultEmailFrom

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
class EnableCronTasks(BooleanPreference):
    section = general
    name = 'enableCronTasks'
    verbose_name = _('Enable Periodic (Cron) Tasks')
    help_text = _(
        'Uncheck this if you will be using crontab, a scheduling service such as Heroku, ' +
        'or if you otherwise do not wish to permit automatic generation of expenses, closing ' +
        'of class registration, etc.'
    )
    default = True


@global_preferences_registry.register
class StaffCategoryInstructor(ModelChoicePreference):
    section = general
    name = 'eventStaffCategoryInstructor'
    verbose_name = _('Instructor Event Staff Category')
    model = EventStaffCategory
    queryset = EventStaffCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return EventStaffCategory.objects.get_or_create(name=_('Class Instruction'))[0]


@global_preferences_registry.register
class StaffCategoryAssistant(ModelChoicePreference):
    section = general
    name = 'eventStaffCategoryAssistant'
    verbose_name = _('Assistant Instructor Event Staff Category')
    model = EventStaffCategory
    queryset = EventStaffCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return EventStaffCategory.objects.get_or_create(name=_('Assistant Class Instruction'))[0]


@global_preferences_registry.register
class StaffCategorySubstitute(ModelChoicePreference):
    section = general
    name = 'eventStaffCategorySubstitute'
    verbose_name = _('Substitute Teacher Event Staff Category')
    model = EventStaffCategory
    queryset = EventStaffCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return EventStaffCategory.objects.get_or_create(name=_('Substitute Teaching'))[0]


@global_preferences_registry.register
class StaffCategoryDJ(ModelChoicePreference):
    section = general
    name = 'eventStaffCategoryDJ'
    verbose_name = _('DJ Event Staff Category')
    model = EventStaffCategory
    queryset = EventStaffCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return EventStaffCategory.objects.get_or_create(name=_('DJ'))[0]


@global_preferences_registry.register
class StaffCategoryOther(ModelChoicePreference):
    section = general
    name = 'eventStaffCategoryOther'
    verbose_name = _('Other Staff Event Staff Category')
    model = EventStaffCategory
    queryset = EventStaffCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return EventStaffCategory.objects.get_or_create(name=_('Other Staff'))[0]


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
class RegistrationDisplayLimitDays(IntegerPreference):
    section = registration
    name = 'displayLimitDays'
    verbose_name = _('Do Not Show Registration for Events that Begin More Than __ Days in the Future')
    help_text = _('By default, events are shown on the registration page as soon as they are created.  If you list events far into the future, set this value, and events that begin more than this many days in the future will not be shown in the registration page.  Enter 0 for no restriction.')
    default = 0


@global_preferences_registry.register
class RegistrationOrgRule(ChoicePreference):
    section = registration
    name = 'orgRule'
    choices = [
        ('SessionFirst', _('Session if available (ordered by start date), otherwise month')),
        ('SessionAlphaFirst', _('Session if available (ordered alphabetically), otherwise month')),
        ('Month', _('Month')),
        ('Session', _('Session ordered by start date (if no session, group as "Other")')),
        ('SessionAlpha', _('Session ordered alphabetically (if no session, group as "Other")')),
        ('SessionMonth',_('Session ordered by start date and Month')),
        ('SessionAlphaMonth',_('Session ordered alphabetically and Month')),
        ('Weekday',_('Weekday')),
        ('MonthWeekday',_('Month and Weekday')),
    ]
    verbose_name = _('Rule for Organizing Series and Events for Registration')
    default = 'SessionFirst'
    help_text = _(
        'In registration, events may be grouped by defined sessions, by month, '
        'the combination of both session and month, or by weekday.'
    )


@global_preferences_registry.register
class EventMonthRule(ChoicePreference):
    section = registration
    name = 'eventMonthRule'
    choices = [
        ('1', _('Month of first occurrence')),
        ('2', _('Month of second occurrence')),
        ('Last', _('Month of last occurrence')),
        ('FirstMulti', _('First month with more than one occurrence (or first)')),
        ('Most', _('Month with the most occurrences')),
    ]
    verbose_name = _('Rule for Assigning Events to Months')
    default = 'FirstMulti'
    help_text = _(
        'When events are listed by month in various views, this rule determines '
        'the month to which each event is assigned.'
    )


@global_preferences_registry.register
class ShowDescriptionRule(ChoicePreference):
    section = registration
    name = 'showDescriptionRule'
    choices = [
        ('0', _('No description')),
        ('10', _('First 10 words')),
        ('20', _('First 20 words')),
        ('50', _('First 50 words')),
        ('all', _('Full description')),
    ]
    verbose_name = _('Rule for showing class descriptions on the regisration page')
    help_text = _(
        'This option determines how much of each event\'s description is shown on the class registration page. '
        'Users can always select the \'more info\' link to access the full description.'
    )
    default = 'all'


@global_preferences_registry.register
class SalesTaxRate(FloatPreference):
    section = registration
    name = 'salesTaxRate'
    verbose_name = _('Sales tax percentage rate to be applied registrations')
    help_text = _('Enter, e.g. \'10\' for a 10% tax rate to be applied to all class and event registrations.')
    default = 0.0


@global_preferences_registry.register
class BuyerPaysSalesTax(BooleanPreference):
    section = registration
    name = 'buyerPaysSalesTax'
    verbose_name = _('Buyer pays sales tax (added to total price)')
    help_text = _('If unchecked, then the buyer will not be charged sales tax directly, but the amount of tax collected by the business will be reported.')
    default = True


@global_preferences_registry.register
class AllowAjaxSignin(BooleanPreference):
    section = registration
    name = 'allowAjaxSignin'
    verbose_name = _('Allow users to login/signup during registration')
    help_text = _('If you don\'t allow customers to see their history or do automatic checks for prerequisites, then you may not need customers to create user accounts or authenticate themselves. If this box is unchecked, then users will not be able to log in or create a new account during the registration process.')
    default = True


@global_preferences_registry.register
class RegistrationSessionExpiryMinutes(IntegerPreference):
    section = registration
    name = 'sessionExpiryMinutes'
    verbose_name = _('Temporary registration data expires after __ minutes')
    help_text = _('In each step of the registration process, customers have this many minutes to proceed before they are no longer guaranteed a spot and are required to begin again.')
    default = 15


@global_preferences_registry.register
class DeleteExpiredTemporaryRegistrations(BooleanPreference):
    section = registration
    name = 'deleteExpiredTemporaryRegistrations'
    verbose_name = _('Automatically delete expired temporary registration and session data')
    help_text = _('If this box is checked, then an hourly script will automatically expired temporary registration and session data.  Disabling this feature is only recommended for testing.')
    default = True


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
class EmailLinkProtocol(ChoicePreference):
    section = email
    name = 'linkProtocol'
    choices = [
        ('http','HTTP'),
        ('https','HTTPS'),
    ]
    verbose_name = _('Protocol for URLs in email templates')
    default = 'http'
    help_text = _(
        'Invoice emails and other emails sometimes include links that require ' +
        'a protocol to be specified via the "protocol" context variable.  If ' +
        'your site uses solely HTTPS, you may need to change this value to avoid ' +
        'broken links.'
    )


@global_preferences_registry.register
class RegSuccessEmailTemplate(ModelChoicePreference):
    section = email
    name = 'registrationSuccessTemplate'
    verbose_name = _('Email template used for successful email registrations')
    model = EmailTemplate
    queryset = EmailTemplate.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():

        initial_template = get_template('email/registration_success.html')
        with open(initial_template.origin.name,'r') as infile:
            content = infile.read()
            infile.close()

        return EmailTemplate.objects.get_or_create(
            name=_('Registration Confirmation Email'),
            defaults={
                'subject': _('Registration Confirmation'),
                'content': content or '',
                'defaultFromAddress': get_defaultEmailFrom(),
                'defaultFromName': get_defaultEmailName(),
                'defaultCC': '',
                'hideFromForm': True,
            }
        )[0]


@global_preferences_registry.register
class InvoiceEmailTemplate(ModelChoicePreference):
    section = email
    name = 'invoiceTemplate'
    verbose_name = _('Email template used for invoice email creation')
    model = EmailTemplate
    queryset = EmailTemplate.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():

        initial_template = get_template('email/invoice_initial.html')
        with open(initial_template.origin.name,'r') as infile:
            content = infile.read()
            infile.close()

        return EmailTemplate.objects.get_or_create(
            name=_('Registration Invoice Email'),
            defaults={
                'subject': _('Registration Invoice'),
                'content': content or '',
                'defaultFromAddress': get_defaultEmailFrom(),
                'defaultFromName': get_defaultEmailName(),
                'defaultCC': '',
                'hideFromForm': True,
            }
        )[0]


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
