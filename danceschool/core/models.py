from django.db import models
from django.contrib.auth.models import User, Group
from django.core.urlresolvers import reverse
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.utils.encoding import python_2_unicode_compatible
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import ugettext_lazy as _

from polymorphic.models import PolymorphicModel
from filer.models import ThumbnailOption
from djangocms_text_ckeditor.fields import HTMLField
import uuid
from datetime import datetime, timedelta
from collections import Counter
import six
from filer.fields.image import FilerImageField
from colorfield.fields import ColorField
from multiselectfield import MultiSelectField
from calendar import month_name, day_name
from djchoices import DjangoChoices, ChoiceItem
from math import ceil
import logging
from jsonfield import JSONField

from cms.models.pluginmodel import CMSPlugin

from .constants import getConstant

if six.PY3:
    # Ensures that checks for Unicode data types (and unicode type assignments) do not break.
    unicode = str


# Define logger for this file
logger = logging.getLogger(__name__)


def get_defaultClassColor():
    ''' Callable for default used by DanceTypeLevel class '''
    return getConstant('calendar__defaultClassColor')


def get_defaultEventCapacity():
    ''' Callable for default used by Location class '''
    return getConstant('registration__defaultEventCapacity')


def get_closeAfterDays():
    ''' Callable for default used by Event class '''
    return getConstant('registration__closeAfterDays')


def get_defaultEmailName():
    ''' Callable for default used by EmailTemplate class '''
    return getConstant('email__defaultEmailName')


def get_defaultEmailFrom():
    ''' Callable for default used by EmailTemplate class '''
    return getConstant('email__defaultEmailFrom')


@python_2_unicode_compatible
class DanceRole(models.Model):
    '''
    Most typically for partnered dances, this will be only Lead and Follow.
    However, it can be generalized to other roles readily, or roles can be
    effectively disabled by simply creating a single role such as "Student."
    '''

    name = models.CharField(max_length=50,unique=True)
    pluralName = models.CharField(max_length=50,unique=True,help_text=_('For the registration form.'))
    order = models.FloatField(help_text=_('Lower numbers show up first when registering.'))

    def save(self, *args, **kwargs):
        ''' Just add "s" if no plural name given. '''

        if not self.pluralName:
            self.pluralName = self.name + 's'

        super(self.__class__, self).save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('order',)


@python_2_unicode_compatible
class DanceType(models.Model):
    '''
    Many dance studios will have only one dance type, but this allows the studio to
    run classes in multiple dance types with different roles for each (e.g. partnered
    vs. non-partnered dances).
    '''
    name = models.CharField(max_length=50,unique=True)
    order = models.FloatField(help_text=_('Lower numbers show up first when choosing class types in the admin.  By default, this does not affect ordering on public-facing registration pages.'))

    roles = models.ManyToManyField(DanceRole,help_text=_('Select default roles used for registrations of this dance type (can be overriden for specific events).'))

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('order',)


@python_2_unicode_compatible
class DanceTypeLevel(models.Model):
    '''
    Levels are defined within dance types.
    '''
    name = models.CharField(max_length=50)
    order = models.FloatField(help_text=_('This is used to order and look up dance types.'))
    danceType = models.ForeignKey(DanceType,verbose_name=_('Dance Type'))

    requiresAudition = models.BooleanField(default=False)

    displayColor = ColorField(verbose_name=_('Display Color'),help_text=_('Choose a color for the calendar display.'),default=get_defaultClassColor)

    def __str__(self):
        return ' - '.join([self.danceType.name, self.name])

    class Meta:
        verbose_name = _('Level of Dance Type')
        verbose_name_plural = _('Levels of dance type')
        ordering = ('danceType__order','order',)


@python_2_unicode_compatible
class StaffMember(PolymorphicModel):
    '''
    StaffMembers include instructors and anyone else who you may wish to
    associate with specific events or activities.
    '''

    # These fields are separate from the user fields because sometimes
    # individuals go publicly by a different name than they may privately.
    firstName = models.CharField(verbose_name=_('First Name'),max_length=50,null=True,blank=True)
    lastName = models.CharField(verbose_name=_('Last Name'),max_length=50,null=True,blank=True)

    # Although Staff members may be defined without user accounts, this precludes
    # them from having access to the school's features, and is not recommended.
    userAccount = models.OneToOneField(User, verbose_name=_('User Account'), null=True,blank=True)

    # By default, only the public email is listed on public-facing pages, and
    # telephone contact information are not listed on public-facing pages either.
    publicEmail = models.CharField(max_length=100,verbose_name=_('Public Email Address'),help_text=_('This is the email address used on the site if the instructor is available for private lessons.'),blank=True)
    privateEmail = models.CharField(max_length=100,verbose_name=_('Private Email Address'),help_text=_('This is the personal email address of the instructor for the instructor directory.'),blank=True)
    phone = models.CharField(max_length=25,help_text=_('Instructor phone numbers are for the instructor directory only, and should not be given to students.'),blank=True,null=True)

    image = FilerImageField(blank=True,null=True,related_name='staff_image')
    bio = HTMLField(verbose_name=_('Bio Text'),help_text=_('Insert the instructor\'s bio here.  Use HTML to include videos, formatting, etc.'),null=True,blank=True)

    # This field is a unique key that is used in the URL for the
    # staff member's personal calendar feed.
    feedKey = models.UUIDField(default=uuid.uuid4,editable=False)

    @property
    def fullName(self):
        return ' '.join([self.firstName or '',self.lastName or ''])

    @property
    def activeThisMonth(self):
        return self.eventstaffmember_set.filter(event__year=datetime.now().year,event__month=datetime.now().month).exists()

    @property
    def activeUpcoming(self):
        return self.eventstaffmember_set.filter(event__endTime__gte=datetime.now()).exists()

    def __str__(self):
        return self.fullName

    class Meta:
        ''' Prevents accidentally adding multiple staff members with the same name. '''
        unique_together = ('firstName', 'lastName')

        permissions = (
            ('view_staff_directory',_('Can access the staff directory view')),
            ('view_school_stats',_('Can view statistics about the school\'s performance.')),
        )


@python_2_unicode_compatible
class Instructor(StaffMember):
    '''
    These go on the instructors page.
    '''
    class InstructorStatus(DjangoChoices):
        roster = ChoiceItem('R',_('Regular Instructor'))
        assistant = ChoiceItem('A',_('Assistant Instructor'))
        training = ChoiceItem('T',_('Instructor-in-training'))
        guest = ChoiceItem('G',_('Guest Instructor'))
        retiredGuest = ChoiceItem('Z',_('Former Guest Instructor'))
        retired = ChoiceItem('X',_('Former/Retired Instructor'))
        hidden = ChoiceItem('H',_('Publicly Hidden'))

    status = models.CharField(max_length=1,choices=InstructorStatus.choices,default=InstructorStatus.roster,help_text=_('Instructor status affects the visibility of the instructor on the site and may also impact the pay rate of the instructor.'))
    availableForPrivates = models.BooleanField(default=True,verbose_name=_('Available For Private Lessons'),help_text=_('Check this box if you would like to be listed as available for private lessons from students.'))

    @property
    def assistant(self):
        return self.status == self.InstructorStatus.assistant

    @property
    def guest(self):
        return self.status == self.InstructorStatus.guest

    @property
    def retired(self):
        return self.status == self.InstructorStatus.retired

    @property
    def hide(self):
        return self.status == self.InstructorStatus.hidden

    @property
    def activeGuest(self):
        return (
            self.status == self.InstructorStatus.guest and
            self.activeUpcoming
        )

    class Meta:
        permissions = (
            ('update_instructor_bio',_('Can update instructors\' bio information')),
            ('view_own_instructor_stats',_('Can view one\'s own statistics (if an instructor)')),
            ('view_other_instructor_stats',_('Can view other instructors\' statistics')),
            ('view_own_instructor_finances',_('Can view one\'s own financial/payment data (if an instructor)')),
            ('view_other_instructor_finances',_('Can view other instructors\' financial/payment data')),
        )


@python_2_unicode_compatible
class ClassDescription(models.Model):
    '''
    All the classes we teach.
    '''
    title = models.CharField(max_length=200)
    description = HTMLField(blank=True)
    danceTypeLevel = models.ForeignKey(DanceTypeLevel,verbose_name=_('Dance Type & Level'),default=1)

    slug = models.SlugField(max_length=100,unique=True,blank='True',help_text=_('This is used in the URL for the individual class pages.  You can override the default'))

    oneTimeSeries = models.BooleanField(verbose_name=_('One Time Series'),default=False,help_text=_('If checked, this class description will not show up in the dropdown menu when creating a new series.'))

    @property
    def danceTypeName(self):
        return self.danceTypeLevel.danceType.name

    @property
    def levelName(self):
        return self.danceTypeLevel.name

    @property
    def lastOffered(self):
        '''
        Returns the start time of the last time this series was offered
        '''
        return self.event_set.order_by('-startTime').first().startTime

    @property
    def lastOfferedMonth(self):
        '''
        Sometimes a Series is associated with a month other than the one
        in which the first class begins, so this returns a (year,month) tuple
        that can be used in admin instead.
        '''
        lastOfferedSeries = self.event_set.order_by('-startTime').first()
        return (lastOfferedSeries.year,lastOfferedSeries.month)

    def __str__(self):
        return self.title

    class Meta:
        '''
        Show descriptions of classes that were most recently offered first.
        '''
        ordering = ('-series__startTime',)


@python_2_unicode_compatible
class Location(models.Model):
    '''
    Events are held at locations.
    '''
    class StatusChoices(DjangoChoices):
        active = ChoiceItem('A',_('Active Location'))
        former = ChoiceItem('F',_('Former Location'))
        specialEvents = ChoiceItem('S',_('Special Event Location (not shown by default)'))

    name = models.CharField(max_length=80,unique=True,help_text=_('Give this location a name.'))

    address = models.CharField(verbose_name='street address',max_length=50,help_text=_('Enter the location\'s street address.'),blank=True,null=True)
    city = models.CharField(max_length=30,default='Cambridge')
    state = models.CharField(verbose_name=_('2-digit state code'),max_length=12,default='MA')
    zip = models.CharField(verbose_name=_('ZIP/postal code'), max_length=12,default='02138')

    directions = HTMLField(help_text=_('Insert any detailed directions that you would like here.  Use HTML to include videos, formatting, etc.'),null=True,blank=True)

    # This property restricts the visibility of the location in dropdowns
    # and on the publicly presented list of locations
    status = models.CharField(max_length=1,help_text=_('Is this location used regularly, used for special events, or no longer used?'),choices=StatusChoices.choices,default=StatusChoices.active)

    orderNum = models.FloatField(default=0,help_text=_('This determines the order that the locations show up on the Locations page.'))

    rentalRate = models.FloatField(null=True,blank=True,verbose_name=_('Hourly Rental Rate (optional)'),help_text=_('When ExpenseItems are created for renting this location, this rental rate will be used to calculate the total cost of rental.'),validators=[MinValueValidator(0)])
    defaultCapacity = models.PositiveIntegerField(_('Default Venue Capacity'),null=True,blank=True,default=get_defaultEventCapacity,help_text=_('If set, this will be used to determine capacity for class series in this venue.'))

    @property
    def address_string(self):
        return self.address + ', ' + self.city + ', ' + self.state + ' ' + self.zip
    address_string.fget.short_description = _('Address')

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('orderNum',)


@python_2_unicode_compatible
class PricingTier(models.Model):
    name = models.CharField(max_length=50,unique=True,help_text=_('Give this pricing tier a name (e.g. \'Default 4-week series\')'))

    # By default, prices may vary by online or door registration, and they may
    # also be adjusted through a student discount.  More sophisticated discounts
    # may be achieved through the discounts and vouchers apps, if enabled.
    onlineStudentPrice = models.FloatField(default=0,validators=[MinValueValidator(0)])
    doorStudentPrice = models.FloatField(default=0,validators=[MinValueValidator(0)])
    onlineGeneralPrice = models.FloatField(default=0,validators=[MinValueValidator(0)])
    doorGeneralPrice = models.FloatField(default=0,validators=[MinValueValidator(0)])

    expired = models.BooleanField(default=False,help_text=_("If this box is checked, then this pricing tier will not show up as an option when creating new series.  Use this for old prices or custom pricing that will not be repeated."))

    def getBasePrice(self,**kwargs):
        '''
        This handles the logic of finding the correct price.  If more sophisticated
        discounting systems are needed, then this PricingTier model can be subclassed,
        or the discounts and vouchers apps can be used.
        '''
        isStudent = kwargs.get('isStudent', False)
        payAtDoor = kwargs.get('payAtDoor', False)

        if isStudent:
            if payAtDoor:
                return self.doorStudentPrice
            return self.onlineStudentPrice
        if payAtDoor:
            return self.doorGeneralPrice
        return self.onlineGeneralPrice

    # basePrice is the non-student, online registration price
    basePrice = property(fget=getBasePrice)

    def __str__(self):
        return self.name


@python_2_unicode_compatible
class EventCategory(models.Model):
    '''
    This abstract base class defines the categorization schema used for
    both public and private events.  If new Events classes are created,
    then their categorization may also inherit from this class.
    '''

    name = models.CharField(max_length=100,unique=True,help_text=_('Category name will be displayed.'))
    description = models.TextField(null=True,blank=True,help_text=_('Add an optional description.'))

    displayColor = ColorField(help_text=_('Choose a color for the calendar display.'),default='#0000FF')

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)
        abstract = True


@python_2_unicode_compatible
class PublicEventCategory(EventCategory):
    '''
    Categorization for public events, inherits from EventCategory.
    '''
    class Meta:
        verbose_name = _('Public event category')
        verbose_name_plural = _('Public event categories')


@python_2_unicode_compatible
class Event(PolymorphicModel):
    '''
    All public and private events, including class series, inherit off of this model.
    '''
    class RegStatus(DjangoChoices):
        disabled = ChoiceItem('D',_('Registration disabled'))
        enabled = ChoiceItem('O',_('Registration enabled'))
        heldClosed = ChoiceItem('K',_('Registration held closed (override default behavior)'))
        heldOpen = ChoiceItem('H',_('Registration held open (override default)'))
        regHidden = ChoiceItem('C',_('Hidden from registration page and registration closed, but visible on calendar.'))
        hidden = ChoiceItem('X',_('Event hidden and registration closed'))

    status = models.CharField(max_length=1,choices=RegStatus.choices,help_text=_('Set the registration status and visibility status of this event.'))

    # Although this can be inferred from status, this field is set in the database
    # to allow simpler queryset operations
    registrationOpen = models.BooleanField(default=False)
    closeAfterDays = models.SmallIntegerField(
        _('Registration Closes Days From First Occurrence'),
        default=get_closeAfterDays,
        null=True,
        blank=True,
        help_text=_('Enter positive values to close after first event occurrence, and negative values to close before first event occurrence.  Leave blank to keep registration open until the event has ended entirely.'))

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    submissionUser = models.ForeignKey(User,null=True,blank=True,related_name='eventsubmissions')

    location = models.ForeignKey(Location,null=True,blank=True)
    capacity = models.PositiveIntegerField(null=True,blank=True)

    # These were formerly methods that were given a property decorator, but
    # we need to store them in the DB so that we can have individual class pages
    # without lots of overhead (we would have to pull the whole set of classes
    # every time someone visited a class page) in order to determine which one was
    # /%year%/%month%/%slug%/.  These fields will not be shown in the admin but will
    # be automatically updated on model save.  They can still be called as they were
    # called before.
    month = models.PositiveSmallIntegerField(null=True,blank=True,validators=[MinValueValidator(1),MaxValueValidator(12)])
    year = models.SmallIntegerField(null=True,blank=True)
    startTime = models.DateTimeField(null=True,blank=True)
    endTime = models.DateTimeField(null=True,blank=True)
    duration = models.FloatField(null=True,blank=True,validators=[MinValueValidator(0)])

    @property
    def getMonthName(self):
        '''
        This exists as a separate method because sometimes events should really
        belong to more than one month (e.g. class series that persist over multiple months).
        '''
        class_counter = Counter([(x.startTime.year, x.startTime.month) for x in self.eventoccurrence_set.all()])
        multiclass_months = [x[0] for x in class_counter.items() if x[1] > 1]
        all_months = [x[0] for x in class_counter.items()]

        if multiclass_months:
            multiclass_months.sort()
            return '/'.join([month_name[x[1]] for x in multiclass_months])

        else:
            return month_name[min(all_months)[1]]

    @property
    def name(self):
        '''
        Since other types of events (PublicEvents, class Series, etc.) are subclasses
        of this class, it is a good idea to override this method for those subclasses,
        to provide a more intuitive name.  However, defining this property at the
        event level ensures that <object>.name can always be used to access a readable
        name for describing the event.
        '''
        if self.startTime:
            return _('Event, begins %s' % (self.startTime.strftime('%a., %B %d, %Y, %I:%M %p')))
        else:
            return _('Event #%s' % (self.id))

    @property
    def description(self):
        '''
        Since other types of events (PublicEvents, class Series, etc.) are subclasses
        of this class, it is a good idea to override this method for those subclasses,
        to provide a more intuitive name.  However, defining this property at the
        event level ensures that <object>.name can always be used to access a description
        for describing the event.
        '''
        return ''

    @property
    def displayColor(self):
        '''
        This property is overridden for Series, for which the display color is set by
        the dance type and level of the class.
        '''
        if hasattr(self,'category') and self.category:
            return self.category.displayColor

    def getBasePrice(self,**kwargs):
        '''
        This method is also generally overridden by subclasses of this class, but it is
        defined here to ensure that the method always exists when looping through events.
        '''
        return None

    # For standard subclasses, basePrice is the non-student, online registration price.
    basePrice = property(fget=getBasePrice)

    def getYearAndMonth(self):

        # Count occurrences by year and month, and find any months with more than one occurrence in them.  Return the
        # first of these.  If no months have more than one occurrence, return the month of the first occurrence.
        class_counter = Counter([(x.startTime.year, x.startTime.month) for x in self.eventoccurrence_set.all()])
        multiclass_months = [x[0] for x in class_counter.items() if x[1] > 1]
        all_months = [x[0] for x in class_counter.items()]

        if multiclass_months:
            return min(multiclass_months)
        elif all_months:
            return min(all_months)
        else:
            return (None,None)

    @property
    def numOccurrences(self):
        return self.eventoccurrence_set.count()
    numOccurrences.fget.short_description = _('# Occurrences')

    @property
    def firstOccurrence(self):
        return self.eventoccurrence_set.order_by('startTime').first()

    @property
    def firstOccurrenceTime(self):
        if self.firstOccurrence:
            return self.firstOccurrence.startTime
        return None
    firstOccurrenceTime.fget.short_description = _('Begins')

    @property
    def nextOccurrence(self):
        return self.eventoccurrence_set.filter(**{'startTime__gte': datetime.now()}).order_by('startTime').first()

    @property
    def nextOccurrenceTime(self):
        if self.nextOccurrence:
            return self.nextOccurrence.startTime
        return None
    nextOccurrenceTime.fget.short_description = _('Next occurs')

    @property
    def lastOccurrence(self):
        return self.eventoccurrence_set.order_by('startTime').last()

    @property
    def lastOccurrenceTime(self):
        if self.lastOccurrence:
            return self.lastOccurrence.endTime
        return None
    lastOccurrenceTime.fget.short_description = _('Ends')

    @property
    def weekday(self):
        return self.firstOccurrenceTime.weekday()
    weekday.fget.short_description = _('Day of week')

    @property
    def hour(self):
        return self.firstOccurrenceTime.hour

    @property
    def minute(self):
        return self.firstOccurrenceTime.minute

    @property
    def isStarted(self):
        return self.firstOccurrenceTime >= datetime.now()
    isStarted.fget.short_description = _('Has begun')

    @property
    def isCompleted(self):
        return self.lastOccurrenceTime < datetime.now()
    isCompleted.fget.short_description = _('Has ended')

    @property
    def registrationEnabled(self):
        ''' Just checks if this event ever permits/permitted registration '''
        return self.status in [self.RegStatus.enabled,self.RegStatus.heldOpen,self.RegStatus.heldClosed]

    @property
    def numDropIns(self):
        return self.eventregistration_set.filter(cancelled=False,dropIn=True).count()
    numDropIns.fget.short_description = _('# Drop-ins')

    @property
    def numRegistered(self):
        return self.eventregistration_set.filter(cancelled=False,dropIn=False).count()
    numRegistered.fget.short_description = _('# Registered')

    @property
    def availableRoles(self):
        '''
        Returns the set of roles for this event.  Since roles are not always custom specified for
        event, this looks for the set of available roles in multiple places.  If no roles are found,
        then the method returns None, in which case it can be assumed that the event's registration
        is not role-specific.
        '''
        eventRoles = self.eventrole_set.filter(capacity__gt=0)
        if eventRoles.count() > 0:
            return [x.role for x in eventRoles]
        elif isinstance(self,Series):
            return self.classDescription.danceTypeLevel.danceType.roles.all()

    def numRegisteredForRole(self, role):
        '''
        Accepts a DanceRole object and returns the number of registrations of that role.
        Ignores errors.
        '''
        try:
            return self.eventregistration_set.filter(cancelled=False,dropIn=False,role=role).count()
        except:
            pass

    def capacityForRole(self,role):
        '''
        Accepts a DanceRole object and determines the capacity for that role at this event.this
        Since roles are not always custom specified for events, this looks for the set of
        available roles in multiple places, and only returns the overall capacity of the event
        if roles are not found elsewhere.
        '''
        eventRoles = self.eventrole_set.filter(capacity__gt=0)
        if eventRoles.count() > 0 and role not in [x.role for x in eventRoles]:
            ''' Custom role capacities exist but role this is not one of them. '''
            return 0
        elif eventRoles.count() > 0:
            ''' The role is a match to custom roles, so check the capacity. '''
            return eventRoles.get(role=role).capacity

        # No custom roles for this event, so get the danceType roles and use the overall
        # capacity divided by the number of roles
        if isinstance(self,Series):
            try:
                availableRoles = self.classDescription.danceTypeLevel.danceType.roles.all()

                if availableRoles.count() > 0 and role not in availableRoles:
                    ''' DanceType roles specified and this is not one of them '''
                    return 0
                elif availableRoles.count() > 0:
                    # Divide the total capacity by the number of roles and round up.
                    return ceil(self.capacity / availableRoles.count())
            except:
                pass

        # No custom roles and no danceType to get roles from, so return the overall capacity
        return self.capacity

    def soldOutForRole(self,role):
        '''
        Accepts a DanceRole object and responds if the number of registrations for that
        role exceeds the capacity for that role at this event.
        '''
        return self.numRegisteredForRole(role) >= self.capacityForRole(role)

    @property
    def soldOut(self):
        return self.numRegistered >= self.capacity
    soldOut.fget.short_description = _('Sold Out')

    @property
    def url(self):
        '''
        This property is typically overwritten by each subclass.
        '''
        return None

    def get_absolute_url(self):
        '''
        This is needed for the creation of calendar feeds.
        '''
        return self.url

    def updateRegistrationStatus(self, saveMethod=False):
        '''
        If called via cron job or otherwise, then update the registrationOpen
        property for this series to reflect any manual override and/or the automatic
        closing of this series for registration.
        '''
        logger.debug('Beginning update registration status.  saveMethod=%s' % saveMethod)

        modified = False
        open = self.registrationOpen

        startTime = self.startTime or getattr(self.eventoccurrence_set.order_by('startTime').first(),'startTime',None)
        endTime = self.endTime or getattr(self.eventoccurrence_set.order_by('-endTime').first(),'endTime',None)

        # If set to these codes, then registration will be held closed
        force_closed_codes = [
            self.RegStatus.disabled,
            self.RegStatus.heldClosed,
            self.RegStatus.regHidden,
            self.RegStatus.hidden
        ]
        # If set to these codes, then registration will be held open
        force_open_codes = [
            self.RegStatus.heldOpen,
        ]

        if self.status in force_closed_codes and open is True:
            open = False
            modified = True
        elif self.status in force_open_codes and open is False:
            open = True
            modified = True
        elif (
            startTime and self.status == self.RegStatus.enabled and ((
                self.closeAfterDays and datetime.now() > startTime + timedelta(days=self.closeAfterDays)) or
                datetime.now() > endTime) and open is True):
                    open = False
                    modified = True
        elif startTime and self.status == self.RegStatus.enabled and ((
            datetime.now() < endTime and not self.closeAfterDays) or (
                self.closeAfterDays and datetime.now() < startTime + timedelta(days=self.closeAfterDays))) and open is False:
                    open = True
                    modified = True

        # Save if something has changed, otherwise, do nothing
        if modified and not saveMethod:
            logger.debug('Attempting to save Series object with status: %s' % open)
            self.registrationOpen = open
            self.save(fromUpdateRegistrationStatus=True)
        logger.debug('Returning value: %s' % open)
        return (modified, open)

    def clean(self):
        if self.status in [Event.RegStatus.enabled, Event.RegStatus.heldOpen] and not self.capacity:
            raise ValidationError(_('If registration is enabled then a capacity must be set.'))

    def save(self, fromUpdateRegistrationStatus=False, *args, **kwargs):
        logger.debug('Save method for Event or subclass called.')

        if fromUpdateRegistrationStatus:
            logger.debug('Avoiding duplicate call to update registration status; ready to save.')
        else:
            logger.debug('About to check registration status and update if needed.')
            modified, open = self.updateRegistrationStatus(saveMethod=True)
            if modified:
                self.registrationOpen = open
            logger.debug('Finished checking status and ready for super call. Value is %s' % self.registrationOpen)
        super(Event,self).save(*args,**kwargs)

    def __str__(self):
        return _('Event: %s' % self.name)

    class Meta:
        verbose_name = _('Series/Event')
        verbose_name_plural = _('All Series/Events')
        ordering = ('-year','-month','-startTime')


@python_2_unicode_compatible
class EventOccurrence(models.Model):
    '''
    All events have one or more occurrences.  For example, class series have classes,
    public events may be one time (one occurrence) or they may occur repeatedly.
    '''
    event = models.ForeignKey(Event)

    startTime = models.DateTimeField(verbose_name=_('Start Time'))
    endTime = models.DateTimeField(verbose_name=_('End Time'))

    cancelled = models.BooleanField(help_text=_('Check this box to mark that the class or event was cancelled.'), default=False)

    @property
    def duration(self):
        '''
        Returns the duration, in hours, for this occurrence
        '''
        return (self.endTime - self.startTime).seconds / 3600

    def allDayForDate(self,this_date):
        '''
        Give a grace period of a few minutes to account for issues with the way
        events are sometimes entered.
        '''
        if type(this_date) is datetime:
            d = this_date.date()
        else:
            d = this_date

        date_start = datetime(d.year,d.month,d.day)
        return (
            self.startTime <= date_start and
            self.endTime >= date_start + timedelta(days=1,minutes=-30)
        )

    @property
    def timeDescription(self):
        startDate = self.startTime.date()
        endDate = self.endTime.date()

        # If all of one date, then just describe it as such
        if self.allDayForDate(startDate) and startDate == endDate:
            return _('On %s' % self.startTime.strftime('%A, %B %d'))

        # Otherwise, describe appropriately
        sameYear = (startDate.year == endDate.year)
        textStrings = []
        for d in [self.startTime,self.endTime]:
            if self.allDayForDate(d) and sameYear:
                textStrings.append(d.strftime('%A, %B %d'))
            elif self.allDayForDate(d):
                textStrings.append(d.strftime('%B %d %Y'))
            else:
                textStrings.append(d.strftime('%B %d, %Y, %l:%M %p'))

        return _('From ') + (_(' to ').join(textStrings))
    timeDescription.fget.short_description = _('Occurs')

    def __str__(self):
        return '%s: %s' % (self.event.name,self.timeDescription)


@python_2_unicode_compatible
class EventRole(models.Model):
    event = models.ForeignKey(Event)
    role = models.ForeignKey(DanceRole)
    capacity = models.PositiveIntegerField()

    class Meta:
        ''' Ensure each role is only listed once per event. '''
        unique_together = ('event','role')


@python_2_unicode_compatible
class EventStaffCategory(models.Model):

    name = models.CharField(max_length=50,unique=True)
    defaultRate = models.FloatField(null=True,blank=True,help_text=_('If the financials app is enabled with automatic generation of expense items, then this is the rate that will be used for staff payments for staff of this type.'),validators=[MinValueValidator(0)])

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = _('Event staff categories')


@python_2_unicode_compatible
class EventStaffMember(models.Model):
    '''
    Events have staff members of various types.  Instructors and
    substitute teachers are defaults, which have their own proxy
    models and managers.  However, other types may be created by
    overriding StaffType.
    '''
    category = models.ForeignKey(EventStaffCategory)

    event = models.ForeignKey(Event)
    occurrences = models.ManyToManyField(EventOccurrence,blank=True)

    staffMember = models.ForeignKey(StaffMember,verbose_name=_('Staff Member'))
    replacedStaffMember = models.ForeignKey('self',verbose_name=_('Replacement for'),related_name='replacementFor',null=True,blank=True)

    # For keeping track of who submitted and when.
    submissionUser = models.ForeignKey(User,verbose_name=_('Submission User'),null=True)
    creationDate = models.DateTimeField(auto_now_add=True)
    modifyDate = models.DateTimeField(auto_now=True)

    @property
    def netHours(self):
        '''
        For regular event staff, this is the net hours worked for financial purposes.
        For Instructors, netHours is caclulated net of any substitutes.
        '''
        if self.category.id in [getConstant('general__eventStaffCategoryAssistantID'),getConstant('general__eventStaffCategoryInstructorID')]:
            return self.event.duration - sum([sub.netHours for sub in self.replacementFor.all()])
        else:
            return sum([x.duration for x in self.occurrences.filter(cancelled=False)])

    def __str__(self):
        replacements = {
            'type': _('Event Staff'),
            'name': self.staffMember.fullName,
            'as': _('as'),
            'category': self.category.name,
            'for': _('for'),
            'eventName': self.event.name,
        }
        return '%(type)s: %(name)s %(as)s %(category)s %(for)s %(eventName)s' % replacements


@python_2_unicode_compatible
class Series(Event):
    '''
    A series is a particular type (subclass) of event which has instructors
    (a subclass of staff).  Series are also matched to a ClassDescription,
    through which their DanceType and DanceTypeLevel are specified.
    '''

    classDescription = models.ForeignKey(ClassDescription,verbose_name=_('Class Description'))

    special = models.BooleanField(verbose_name=_('Special Class/Series'),default=False,help_text=_('Special classes (e.g. one-offs, visiting instructors) may be listed separately on the class page.  Leave this unchecked for regular monthly series classes.'))
    allowDropins = models.BooleanField(verbose_name=_('Allow Class Drop-ins'), default=False, help_text=_('If checked, then staff will be able to register students as drop-ins.'))

    def getTeachers(self,includeSubstitutes=False):
        seriesTeachers = SeriesTeacher.objects.filter(event=self)
        seriesTeachers = set([t.staffMember for t in seriesTeachers])

        if includeSubstitutes:
            for c in self.eventoccurrence_set:
                sts = SubstituteTeacher.objects.filter(classes=c)
                for s in sts:
                    seriesTeachers.add(s.staffMember)

        return list(seriesTeachers)

    teachers = property(fget=getTeachers)

    pricingTier = models.ForeignKey(PricingTier,verbose_name=_('Pricing Tier'))

    dropinPrice = models.FloatField(_('Drop-in price'),default=15,null=True,blank=True,validators=[MinValueValidator(0)])

    @property
    def name(self):
        '''
        Overrides property from Event base class.
        '''
        return self.classDescription.title

    @property
    def description(self):
        '''
        Overrides property from Event base class.
        '''
        return self.classDescription.title

    @property
    def slug(self):
        '''
        No property in the Event base class, but PublicEvents have a slug field, so this allows
        us to iterate over that property in templates
        '''
        return self.classDescription.slug

    @property
    def displayColor(self):
        '''
        Overrides property from Event base class.
        '''
        return self.classDescription.danceTypeLevel.displayColor

    def getBasePrice(self,**kwargs):
        '''
        This method overrides the method of the base Event class by
        checking the pricingTier associated with this Series and getting
        the appropriate price for it.
        '''
        if not self.pricingTier:
            return None
        return self.pricingTier.getBasePrice(**kwargs)

    # base price is the non-student, online registration price.
    basePrice = property(fget=getBasePrice)

    @property
    def url(self):
            return reverse('classView',args=[self.year,month_name[self.month],self.classDescription.slug])

    def clean(self):
        if self.allowDropins and not self.dropinPrice:
            raise ValidationError(_('If drop-ins are allowed then drop-in price must be specified.'))
        super(Series,self).clean()

    def __str__(self):
        if self.month and self.year:
            # In case of unsaved series, month and year are not yet set.
            return month_name[self.month] + ' ' + str(self.year) + ": " + self.classDescription.title
        else:
            return _('Class Series: %s' % self.classDescription.title)

    class Meta:
        verbose_name = _('Class Series')
        verbose_name_plural = _('Class series')


class SeriesTeacherManager(models.Manager):
    '''
    Limits SeriesTeacher queries to only staff reported as teachers, and ensures that
    these individuals are reported as teachers when created.
    '''

    def get_queryset(self):
        return super(SeriesTeacherManager,self).get_queryset().filter(
            category__id=getConstant('general__eventStaffCategoryInstructorID')
        )

    def create(self, **kwargs):
        kwargs.update({
            'category': getConstant('general__eventStaffCategoryInstructorID'),
            'occurrences': kwargs.get('event').eventoccurrence_set.all(),
        })
        return super(SeriesTeacherManager,self).create(**kwargs)


@python_2_unicode_compatible
class SeriesTeacher(EventStaffMember):
    '''
    A proxy model that provides staff member properties specific to
    keeping track of series teachers.
    '''
    objects = SeriesTeacherManager()

    @property
    def netHours(self):
        '''
        For regular event staff, this is the net hours worked for financial purposes.
        For Instructors, netHours is calculated net of any substitutes.
        '''
        return self.event.duration - sum([sub.netHours for sub in self.replacementFor.all()])

    def __str__(self):
        return str(self.staffMember) + " - " + str(self.event)

    class Meta:
        proxy = True


class SubstituteTeacherManager(models.Manager):
    '''
    Limits SeriesTeacher queries to only staff reported as teachers, and ensures that
    these individuals are reported as teachers when created.
    '''

    def get_queryset(self):
        return super(SubstituteTeacherManager,self).get_queryset().filter(
            category__id=getConstant('general__eventStaffCategorySubstituteID')
        )

    def create(self, **kwargs):
        kwargs.update({
            'category': getConstant('general__eventStaffCategorySubstituteID')})
        return super(SubstituteTeacherManager,self).create(**kwargs)


@python_2_unicode_compatible
class SubstituteTeacher(EventStaffMember):
    '''
    Keeps track of substitute teaching.  The series and seriesTeacher fields are both needed, because
    this allows the substitute teaching inline to be displayed for each series.
    '''
    objects = SubstituteTeacherManager()

    def __str__(self):
        replacements = {
            'name': self.staffMember.fullName,
            'subbed': _(' subbed: '),
            'month': month_name[self.event.month],
            'year': self.event.year,
        }
        if not self.replacedStaffMember:
            return '%(name)s %(subbed)s: %(month)s %(year)s' % replacements

        replacements.update({'subbed': _(' subbed for '), 'staffMember': self.replacedStaffMember.staffMember.fullName})
        return '%(name)s %(subbed)s %(staffMember)s: %(month)s %(year)s' % replacements

    def clean(self):
        ''' Ensures no SubstituteTeacher without indicating who they replaced. '''
        if not self.replacedStaffMember:
            raise ValidationError(_('Must indicate which Instructor was replaced.'))

    class Meta:
        proxy = True
        permissions = (
            ('report_substitute_teaching',_('Can access the substitute teaching reporting form')),
        )


@python_2_unicode_compatible
class PublicEvent(Event):
    '''
    Special Events which may have their own display page.
    '''

    title = models.CharField(max_length=100,help_text=_('Give the event a title'))
    slug = models.SlugField(max_length=100,help_text=_('This is for the event page URL, you can override the default.'))

    category = models.ForeignKey(PublicEventCategory,null=True,blank=True)
    descriptionField = HTMLField(null=True,blank=True,verbose_name=_('Description'),help_text=_('Describe the event for the event page.'))
    link = models.URLField(blank=True,null=True,help_text=_('Optionally include the URL to a page for this Event.  If set, then the site\'s auto-generated Event page will instead redirect to this URL.'))

    # The pricing tier is optional, but registrations cannot be enabled unless a pricing tier is
    # specified (the pricing tier may specify the price as free for Free events).
    pricingTier = models.ForeignKey(PricingTier,null=True,blank=True,verbose_name=_('Pricing Tier'))

    def getBasePrice(self,**kwargs):
        '''
        This method overrides the method of the base Event class by
        checking the pricingTier associated with this PublicEvent and getting
        the appropriate price for it.
        '''
        if not self.pricingTier:
            return None
        return self.pricingTier.getBasePrice(**kwargs)

    # The base price is the non-student, online registration price.
    basePrice = property(fget=getBasePrice)

    @property
    def name(self):
        '''
        Overrides property from Event base class.
        '''
        return self.title

    @property
    def description(self):
        '''
        Overrides property from Event base class.
        '''
        return self.descriptionField

    @property
    def url(self):
            return reverse('eventView',args=[self.year,month_name[self.month],self.slug])

    def __str__(self):
        try:
            return self.name + ': ' + self.eventoccurrence_set.first().startTime.strftime('%a., %B %d, %Y, %I:%M %p')
        except:
            return self.name

    class Meta:
        verbose_name = _('Public event')


@python_2_unicode_compatible
class Customer(models.Model):
    '''
    Not all customers choose to log in when they sign up for classes, and sometimes Users register their spouses, friends,
    or other customers.  However, we still need to keep track of those customers' registrations.  So, Customer objects
    are unique for each combination of name and email address, even though Users are unique by email address only.  Customers
    also store name and email information separately from the User object.
    '''
    user = models.OneToOneField(User,null=True,blank=True)

    first_name = models.CharField(_('first name'), max_length=30)
    last_name = models.CharField(_('last name'), max_length=30)
    email = models.EmailField(_('email address'))
    phone = models.CharField(_('telephone'),max_length=20,null=True,blank=True)

    # PostgreSQL can store arbitrary additional information associated with this customer
    # in a JSONfield, but to remain database agnostic we are using django-jsonfield
    data = JSONField(default={})

    @property
    def fullName(self):
        return ' '.join([self.first_name or '',self.last_name or ''])

    @property
    def numEventRegistrations(self):
        return EventRegistration.objects.filter(registration__customer=self).count()
    numEventRegistrations.fget.short_description = _('# Events/Series Registered')

    @property
    def numClassSeries(self):
        return EventRegistration.objects.filter(registration__customer=self,event__series__isnull=False).count()
    numEventRegistrations.fget.short_description = _('# Series Registered')

    @property
    def numPublicEvents(self):
        return EventRegistration.objects.filter(registration__customer=self,event__publicevent__isnull=False).count()
    numEventRegistrations.fget.short_description = _('# Public Events Registered')

    def getSeriesRegistered(self,q_filter=Q(),distinct=True,counter=False,**kwargs):
        '''
        Return a list that indicates each series the person has registered for
        and how many registrations they have for that series (because of couples).
        This can be filtered by any keyword arguments passed (e.g. year and month).
        '''
        series_set = Series.objects.filter(q_filter,eventregistration__registration__customer=self,**kwargs)

        if not distinct:
            return series_set
        elif distinct and not counter:
            return series_set.distinct()
        elif 'year' in kwargs or 'month' in kwargs:
            return [str(x[1]) + 'x: ' + x[0].classDescription.title for x in Counter(series_set).items()]
        else:
            return [str(x[1]) + 'x: ' + x[0].__str__() for x in Counter(series_set).items()]

    def getMultiSeriesRegistrations(self,q_filter=Q(),name_series=False,**kwargs):
        '''
        Use the getSeriesRegistered method above to get a list of each series the
        person has registered for.  The return only indicates whether they are
        registered more than once for the same series (e.g. for keeping track of
        dance admissions for couples who register under one name).
        '''
        series_registered = self.getSeriesRegistered(q_filter,distinct=False,counter=False,**kwargs)
        counter_items = Counter(series_registered).items()
        multireg_list = [x for x in counter_items if x[1] > 1]

        if name_series and multireg_list:
            if 'year' in kwargs or 'month' in kwargs:
                return [str(x[1]) + 'x: ' + x[0].classDescription.title for x in multireg_list]
            else:
                return [str(x[1]) + 'x: ' + x[0].__str__() for x in multireg_list]
        elif multireg_list:
            return '%sx registration' % max([x[1] for x in multireg_list])

    def __str__(self):
        return '%s: %s' % (self.fullName, self.email)

    class Meta:
        unique_together = ('last_name','first_name','email')
        ordering = ('last_name','first_name')
        permissions = (
            ('can_autocomplete_users',_('Able to use customer and User autocomplete features (in various admin forms)')),
            ('view_other_user_profiles',_('Able to view other Customer and User profile pages')),
        )


@python_2_unicode_compatible
class TemporaryRegistration(models.Model):
    firstName = models.CharField(max_length=100)
    lastName = models.CharField(max_length=100)
    email = models.CharField(max_length=200)
    phone = models.CharField(max_length=20,null=True,blank=True)

    howHeardAboutUs = models.TextField(_('How they heard about us'),default='',blank=True,null=True)
    student = models.BooleanField(default=False)
    payAtDoor = models.BooleanField(default=False)

    submissionUser = models.ForeignKey(User, verbose_name=_('registered by user'),related_name='submittedtemporaryregistrations',null=True,blank=True)

    comments = models.TextField(default='')
    dateTime = models.DateTimeField(blank=True,null=True)
    priceWithDiscount = models.FloatField(verbose_name=_('price net of discounts'),null=True,validators=[MinValueValidator(0)])

    # PostgreSQL can store arbitrary additional information associated with this registration
    # in a JSONfield, but to remain database-agnostic we are using django-jsonfield.  This allows
    # hooked in registration-related procedures to hang on to miscellaneous data
    # for the duration of the registration process without having to create models in another app.
    # By default (and for security reasons), the registration system ignores any passed data that it does not
    # expect, so you will need to hook into the registration system to ensure that any extra information that
    # you want to use is not discarded.
    data = JSONField(null=True,blank=True)

    @property
    def fullName(self):
        return ' '.join([self.firstName,self.lastName])

    @property
    def seriesPrice(self):
        return self.temporaryeventregistration_set.filter(Q(event__series__isnull=False)).aggregate(Sum('price')).get('price__sum')

    @property
    def publicEventPrice(self):
        return self.temporaryeventregistration_set.filter(Q(event__publicevent__isnull=False)).aggregate(Sum('price')).get('price__sum')

    @property
    def totalPrice(self):
        return self.temporaryeventregistration_set.aggregate(Sum('price')).get('price__sum')

    @property
    def totalDiscount(self):
        return self.totalPrice - self.priceWithDiscount

    def __str__(self):
        if self.dateTime:
            return '%s #%s: %s, %s' % (_('Temporary Registration'), self.id, self.fullName, self.dateTime.strftime('%b. %Y'))
        else:
            return '%s #%s: %s' % (_('Temporary Registration'), self.id, self.fullName)

    class Meta:
        ordering = ('-dateTime',)


@python_2_unicode_compatible
class Registration(models.Model):
    '''
    There is a single registration for an online transaction.
    A single Registration includes multiple classes, as well as events.
    '''
    firstName = models.CharField(max_length=100,default='TBD')
    lastName = models.CharField(max_length=100,default='TBD')
    customer = models.ForeignKey(Customer)

    howHeardAboutUs = models.TextField(_('How they heard about us'),default='',blank=True,null=True)
    student = models.BooleanField(default=False)
    payAtDoor = models.BooleanField(default=False)

    comments = models.TextField(default='',blank=True,null=True)
    paidOnline = models.BooleanField(default=False,verbose_name=_('Paid Online'))
    submissionUser = models.ForeignKey(User,null=True,blank=True,verbose_name=_('registered by user'),related_name='submittedregistrations')
    collectedByUser = models.ForeignKey(User,null=True,blank=True,verbose_name=_('Collected by user'),related_name='collectedregistrations')
    processingFee = models.FloatField(default=0,verbose_name=_('Processing Fees'),validators=[MinValueValidator(0)])
    priceWithDiscount = models.FloatField(verbose_name=_('Price Net of Discounts'),validators=[MinValueValidator(0)])
    amountPaid = models.FloatField(default=0,verbose_name=_('Net Amount Paid'),validators=[MinValueValidator(0)])
    dateTime = models.DateTimeField(blank=True,null=True,verbose_name=_('Date & Time'))
    invoiceNumber = models.CharField(_('Invoice Number'),null=True,blank=True,max_length=80)

    temporaryRegistration = models.OneToOneField(TemporaryRegistration,null=True)

    # PostgreSQL can store arbitrary additional information associated with this registration
    # in a JSONfield, but to remain database-agnostic we are using django-jsonfield
    data = JSONField(null=True,blank=True)

    @property
    def fullName(self):
        return self.customer.fullName

    @property
    def seriesPrice(self):
        return self.eventregistration_set.filter(Q(event__series__isnull=False)).aggregate(Sum('price')).get('price__sum') or 0

    @property
    def publicEventPrice(self):
        return self.eventregistration_set.filter(Q(event__publicevent__isnull=False)).aggregate(Sum('price')).get('price__sum') or 0

    @property
    def totalPrice(self):
        return self.eventregistration_set.aggregate(Sum('price')).get('price__sum')

    # This alias just makes it easier to register properties in other apps.
    @property
    def netPrice(self):
        return self.priceWithDiscount

    # For now, revenue is allocated proportionately between series and events
    # as a percentage of the discounted total amount paid.  Ideally, revenue would
    # be allocated by applying discounts proportionately only to the items for which
    # they apply.  However, this has not been implemented.
    @property
    def seriesNetPrice(self):
        if self.totalPrice == 0:
            return 0
        return self.priceWithDiscount * (self.seriesPrice / self.totalPrice)

    @property
    def eventNetPrice(self):
        if self.totalPrice == 0:
            return 0
        return self.priceWithDiscount * (self.publicEventPrice / self.totalPrice)

    @property
    def seriesAmountPaid(self):
        if self.totalPrice == 0:
            return 0
        return self.amountPaid * (self.seriesPrice / self.totalPrice)

    @property
    def eventAmountPaid(self):
        if self.totalPrice == 0:
            return 0
        return self.amountPaid * (self.publicEventPrice / self.totalPrice)

    @property
    def voucherAmount(self):
        return sum([x.amount for x in self.voucheruse_set.all()])

    @property
    def seriesVoucherAmount(self):
        if self.totalPrice == 0:
            return 0
        else:
            return self.voucherAmount * (self.seriesPrice / self.totalPrice)

    @property
    def eventVoucherAmount(self):
        if self.totalPrice == 0:
            return 0
        else:
            return self.voucherAmount * (self.publicEventPrice / self.totalPrice)

    def getSeriesPriceForMonth(self,dateOfInterest):
        # get all series associated with this registration
        return sum([x.price for x in self.eventregistration_set.filter(series__year=dateOfInterest.year,series__month=dateOfInterest.month).filter(Q(event__series__isnull=False))])

    def getEventPriceForMonth(self,dateOfInterest):
        # get all series associated with this registration
        return sum([x.price for x in self.eventregistration_set.filter(series__year=dateOfInterest.year,series__month=dateOfInterest.month).filter(Q(event__publicevent__isnull=False))])

    def getPriceForMonth(self,dateOfInterest):
        return sum([x.price for x in self.eventregistration_set.filter(series__year=dateOfInterest.year,series__month=dateOfInterest.month)])

    def getSeriesAmountPaidForMonth(self,dateOfInterest):
        # get total price for series of this month
        if self.seriesPrice == 0:
            return 0
        else:
            return self.seriesAmountPaid * (self.getSeriesPriceForMonth(dateOfInterest) / self.seriesPrice)

    def getEventAmountPaidForMonth(self,dateOfInterest):
        # get total price for series of this month
        if self.publicEventPrice == 0:
            return 0
        else:
            return self.eventAmountPaid * (self.getEventPriceForMonth(dateOfInterest) / self.publicEventPrice)

    def getAmountPaidForMonth(self,dateOfInterest):
        return self.getSeriesAmountPaidForMonth(dateOfInterest) + self.getEventAmountPaidForMonth(dateOfInterest)

    def getProcessingFeeForMonth(self,dateOfInterest):
        if self.amountPaid == 0:
            return 0
        else:
            return self.processingFee * self.getAmountPaidForMonth(dateOfInterest) / self.amountPaid

    def __str__(self):
        if self.dateTime:
            return '%s #%s: %s, %s' % (_('Registration'), self.id, self.customer.fullName, self.dateTime.strftime('%b. %Y'))
        else:
            return '%s #%s: %s' % (_('Registration'), self.id, self.customer.fullName)

    class Meta:
        ordering = ('-dateTime',)

        permissions = (
            ('view_registration_summary',_('Can access the series-level registration summary view')),
            ('checkin_customers',_('Can check-in customers using the summary view')),
            ('accept_door_payments',_('Can process door payments in the registration system')),
            ('send_invoices',_('Can send invoices to students requesting payment')),
            ('register_dropins',_('Can register students for drop-ins.')),
            ('override_register_closed',_('Can register students for series/events that are closed for registration by the public')),
            ('override_register_soldout',_('Can register students for series/events that are officially sold out')),
            ('override_register_dropins',_('Can register students for drop-ins even if the series does not allow drop-in registration.')),
        )


@python_2_unicode_compatible
class EventRegistration(models.Model):
    '''
    An EventRegistration is associated with a Registration and records
    a registration for a single event.
    '''
    registration = models.ForeignKey(Registration)
    event = models.ForeignKey(Event)
    customer = models.ForeignKey(Customer)
    role = models.ForeignKey(DanceRole, null=True,blank=True)
    price = models.FloatField(default=0,validators=[MinValueValidator(0)])

    checkedIn = models.BooleanField(default=False,help_text=_('Check to mark the individual as checked in.'),verbose_name=_('Checked In'))

    dropIn = models.BooleanField(default=False,help_text=_('If true, this is a drop-in registration.'),verbose_name=_('Drop-in registration'))
    cancelled = models.BooleanField(default=False,help_text=_('Mark as cancelled so that this registration is not counted in student/attendee counts.'))

    # PostgreSQL can store arbitrary additional information associated with this registration
    # in a JSONfield, but to remain database-agnostic we are using django-jsonfield
    data = JSONField(default={})

    @property
    def netPrice(self):
        if self.registration.totalPrice == 0:
            return 0
        return self.price * (self.registration.netPrice / self.registration.totalPrice)

    @property
    def discounted(self):
        return (self.price != self.netPrice)

    @property
    def matchingTemporaryRegistration(self):
        return self.registration.temporaryRegistration.temporaryeventregistration_set.get(event=self.event)

    def __str__(self):
        return str(self.customer) + " " + str(self.event)


class TemporaryEventRegistration(models.Model):
    price = models.FloatField(validators=[MinValueValidator(0)])
    event = models.ForeignKey(Event)
    role = models.ForeignKey(DanceRole,null=True,blank=True)
    dropIn = models.BooleanField(default=False,help_text=_('If true, this is a drop-in registration.'),verbose_name=_('Drop-in registration'))

    registration = models.ForeignKey(TemporaryRegistration)

    # PostgreSQL can store arbitrary additional information associated with this registration
    # in a JSONfield, but to remain database-agnostic we are using django-jsonfield
    data = JSONField(default={})


@python_2_unicode_compatible
class EmailTemplate(models.Model):
    name = models.CharField(max_length=100,unique=True)
    subject = models.CharField(max_length=200,null=True,blank=True)
    content = models.TextField(null=True,blank=True,help_text=_('See the list of available variables for details on what information can be included with template tags.'))
    defaultFromName = models.CharField(verbose_name=_('From Name (default)'),max_length=100,null=True,blank=True,default=get_defaultEmailName)
    defaultFromAddress = models.EmailField(verbose_name=_('From Address (default)'),max_length=100,null=True,blank=True,default=get_defaultEmailFrom)
    defaultCC = models.CharField(verbose_name=_('CC (default)'),max_length=100,null=True,blank=True)

    groupRequired = models.ForeignKey(Group,verbose_name=_('Group permissions required to use.'),null=True,blank=True,help_text=_('Some templates should only be visible to some users.'))
    hideFromForm = models.BooleanField(_('Hide from \'Email Students\' Form'),default=False,help_text=_('Check this box for templates that are used for automated emails.'))

    def __str__(self):
        return self.name

    class Meta:
        permissions = (
            ('send_email',_('Can send emails using the SendEmailView')),
        )


class StaffMemberPluginModel(CMSPlugin):
    ''' Views on an individual staff member or instructor use this model for configuration. '''
    staffMember = models.ForeignKey(StaffMember)
    template = models.CharField(max_length=250,null=True,blank=True)


class InstructorListPluginModel(CMSPlugin):
    '''
    The Instructor photo list, instructor bio listing, and instructor directory all use this model for configuration.
    '''

    class OrderChoices(DjangoChoices):
        firstName = ChoiceItem('firstName',_('First Name'))
        lastName = ChoiceItem('lastName',_('Last Name'))
        status = ChoiceItem('status',_('Instructor Status'))
        random = ChoiceItem('random',_('Randomly Ordered'))

    statusChoices = MultiSelectField(
        verbose_name=_('Limit to Instructor Status'),
        choices=Instructor.InstructorStatus.choices,
        default=[Instructor.InstructorStatus.roster,Instructor.InstructorStatus.assistant,Instructor.InstructorStatus.guest]
    )
    orderChoice = models.CharField(verbose_name=_('Order By'),max_length=10,choices=OrderChoices.choices)
    imageThumbnail = models.ForeignKey(ThumbnailOption,verbose_name=_('Image thumbnail option'),null=True,blank=True)

    bioRequired = models.BooleanField(verbose_name=_('Exclude instructors with no bio'),default=False)
    photoRequired = models.BooleanField(verbose_name=_('Exclude instructors with no photo'),default=False)
    activeUpcomingOnly = models.BooleanField(verbose_name=_('Include only instructors with upcoming classes'),default=False)

    title = models.CharField(verbose_name=_('Listing Title'),max_length=200,null=True,blank=True)
    template = models.CharField(verbose_name=_('Template'),max_length=250,null=True,blank=True)


class LocationListPluginModel(CMSPlugin):
    ''' A model for listing of all active locations '''
    template = models.CharField(verbose_name=_('Template'),max_length=250,null=True,blank=True)


class LocationPluginModel(CMSPlugin):
    ''' Individual location directions, etc. use this view '''
    location = models.ForeignKey(Location,verbose_name=_('Location'))
    template = models.CharField(verbose_name=_('Template'),max_length=250,null=True,blank=True)


class EventListPluginModel(CMSPlugin):
    '''
    This model is typically used to configure upcoming event listings, but it can be customized to a variety of purposes using
    custom templates, etc.
    '''
    LIMIT_CHOICES = [
        ('S',_('Event start date')),
        ('E',_('Event end date')),
    ]

    title = models.CharField(max_length=250,verbose_name=_('Custom List Title'),default=_('Upcoming Events'),blank=True)

    eventType = models.CharField(max_length=1,verbose_name=_('Limit to Event Type'),choices=(('S',_('Class Series')),('P',_('Public Events'))),null=True,blank=True,help_text=_('Leave blank to include all Events.'))

    limitTypeStart = models.CharField(max_length=1,verbose_name=_('Limit interval start by'),choices=LIMIT_CHOICES,default='E')
    daysStart = models.SmallIntegerField(verbose_name=_('Interval limited to __ days from present'),null=True,blank=True,help_text=_('(E.g. enter -30 for an interval that starts with 30 days prior to today) Leave blank for no limit, or enter 0 to limit to future events'))
    startDate = models.DateField(verbose_name=_('Exact interval start date'),null=True,blank=True,help_text=_('Leave blank for no limit (overrides relative interval limits)'))

    limitTypeEnd = models.CharField(max_length=1,verbose_name=_('Limit interval end by'),choices=LIMIT_CHOICES,default='S')
    daysEnd = models.SmallIntegerField(verbose_name=_('Interval limited to __ days from present'),null=True,blank=True,help_text=_('(E.g. enter 30 for an interval that ends 30 days from today) Leave blank for no limit, or enter 0 to limit to past events'))
    endDate = models.DateField(verbose_name=_('Exact interval end date '),null=True,blank=True,help_text=_('Leave blank for no limit (overrides relative interval limits)'))

    limitToOpenRegistration = models.BooleanField(verbose_name=_('Limit to open for registration only'),default=False)

    location = models.ForeignKey(Location,verbose_name=_('Limit to Location'),null=True,blank=True)
    weekday = models.PositiveSmallIntegerField(verbose_name=_('Limit to Weekday'),null=True,blank=True,choices=[(x,day_name[x]) for x in range(0,7)])

    cssClasses = models.CharField(max_length=250,verbose_name=_('Custom CSS Classes'),null=True,blank=True,help_text=_('Classes are applied to surrounding &lt;div&gt;'))
    template = models.CharField(max_length=250,null=True,blank=True)

    class Meta:
        permissions = (
            ('choose_custom_plugin_template',_('Can enter a custom plugin template for plugins with selectable template.')),
        )
