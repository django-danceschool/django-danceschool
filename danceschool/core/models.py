from django.db import models
from django.contrib.auth.models import User, Group
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db.models import Q, Sum
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import ugettext_lazy as _
from django.apps import apps
from django.utils import timezone

from polymorphic.models import PolymorphicModel
from filer.models import ThumbnailOption
from djangocms_text_ckeditor.fields import HTMLField
import uuid
from datetime import datetime, timedelta
from collections import Counter
from filer.fields.image import FilerImageField
from colorful.fields import RGBColorField
from multiselectfield import MultiSelectField
from calendar import month_name, day_name
from djchoices import DjangoChoices, ChoiceItem
from math import ceil
from itertools import accumulate
import logging
from jsonfield import JSONField
import string
import random

from cms.models.pluginmodel import CMSPlugin

from .constants import getConstant
from .signals import post_registration
from .mixins import EmailRecipientMixin
from .utils.emails import get_text_for_html
from .utils.timezone import ensure_localtime


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


def get_validationString():
    return ''.join(random.choice(string.ascii_uppercase) for i in range(25))


class DanceRole(models.Model):
    '''
    Most typically for partnered dances, this will be only Lead and Follow.
    However, it can be generalized to other roles readily, or roles can be
    effectively disabled by simply creating a single role such as "Student."
    '''

    name = models.CharField(_('Name'),max_length=50,unique=True)
    pluralName = models.CharField(_('Plural of name'),max_length=50,unique=True,help_text=_('For the registration form.'))
    order = models.FloatField(_('Order number'),help_text=_('Lower numbers show up first when registering.'))

    def save(self, *args, **kwargs):
        ''' Just add "s" if no plural name given. '''

        if not self.pluralName:
            self.pluralName = self.name + 's'

        super(self.__class__, self).save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Dance role')
        verbose_name_plural = _('Dance roles')
        ordering = ('order',)


class DanceType(models.Model):
    '''
    Many dance studios will have only one dance type, but this allows the studio to
    run classes in multiple dance types with different roles for each (e.g. partnered
    vs. non-partnered dances).
    '''
    name = models.CharField(_('Name'),max_length=50,unique=True)
    order = models.FloatField(_('Order number'),help_text=_('Lower numbers show up first when choosing class types in the admin.  By default, this does not affect ordering on public-facing registration pages.'))

    roles = models.ManyToManyField(DanceRole,verbose_name=_('Dance roles'),help_text=_('Select default roles used for registrations of this dance type (can be overriden for specific events).'))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Dance type')
        verbose_name_plural = _('Dance types')
        ordering = ('order',)


class DanceTypeLevel(models.Model):
    '''
    Levels are defined within dance types.
    '''
    name = models.CharField(_('Name'),max_length=50)
    order = models.FloatField(_('Order number'),help_text=_('This is used to order and look up dance types.'))
    danceType = models.ForeignKey(DanceType,verbose_name=_('Dance Type'),on_delete=models.CASCADE)

    displayColor = RGBColorField(_('Display Color'),help_text=_('Choose a color for the calendar display.'),default=get_defaultClassColor)

    def __str__(self):
        return ' - '.join([self.danceType.name, self.name])

    class Meta:
        verbose_name = _('Level of dance type')
        verbose_name_plural = _('Levels of dance type')
        ordering = ('danceType__order','order',)


class StaffMember(PolymorphicModel):
    '''
    StaffMembers include instructors and anyone else who you may wish to
    associate with specific events or activities.
    '''

    # These fields are separate from the user fields because sometimes
    # individuals go publicly by a different name than they may privately.
    firstName = models.CharField(_('First name'),max_length=50,null=True,blank=True)
    lastName = models.CharField(_('Last name'),max_length=50,null=True,blank=True)

    # Although Staff members may be defined without user accounts, this precludes
    # them from having access to the school's features, and is not recommended.
    userAccount = models.OneToOneField(User, verbose_name=_('User account'), null=True,blank=True,on_delete=models.SET_NULL)

    # By default, only the public email is listed on public-facing pages, and
    # telephone contact information are not listed on public-facing pages either.
    publicEmail = models.CharField(_('Public Email Address'),max_length=100,help_text=_('This is the email address used on the site if the instructor is available for private lessons.'),blank=True)
    privateEmail = models.CharField(_('Private Email Address'),max_length=100,help_text=_('This is the personal email address of the instructor for the instructor directory.'),blank=True)
    phone = models.CharField(_('Telephone'),max_length=25,help_text=_('Instructor phone numbers are for the instructor directory only, and should not be given to students.'),blank=True,null=True)

    image = FilerImageField(verbose_name=_('Staff photo'),blank=True,null=True,related_name='staff_image')
    bio = HTMLField(verbose_name=_('Bio text'),help_text=_('Insert the instructor\'s bio here.  Use HTML to include videos, formatting, etc.'),null=True,blank=True)

    # This field is a unique key that is used in the URL for the
    # staff member's personal calendar feed.
    feedKey = models.UUIDField(verbose_name=_('Calendar/RSS feed key'),default=uuid.uuid4,editable=False)

    @property
    def fullName(self):
        return ' '.join([self.firstName or '',self.lastName or ''])
    fullName.fget.short_description = _('Name')

    @property
    def activeThisMonth(self):
        return self.eventstaffmember_set.filter(event__year=timezone.now().year,event__month=timezone.now().month).exists()
    activeThisMonth.fget.short_description = _('Staffed this month')

    @property
    def activeUpcoming(self):
        return self.eventstaffmember_set.filter(event__endTime__gte=timezone.now()).exists()
    activeUpcoming.fget.short_description = _('Staffed for upcoming events')

    def __str__(self):
        return self.fullName

    class Meta:
        ''' Prevents accidentally adding multiple staff members with the same name. '''
        unique_together = ('firstName', 'lastName')
        verbose_name = _('Staff member')
        verbose_name_plural = _('Staff members')
        ordering = ('lastName','firstName')

        permissions = (
            ('view_staff_directory',_('Can access the staff directory view')),
            ('view_school_stats',_('Can view statistics about the school\'s performance.')),
        )


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

    status = models.CharField(_('Instructor status'),max_length=1,choices=InstructorStatus.choices,default=InstructorStatus.roster,help_text=_('Instructor status affects the visibility of the instructor on the site and may also impact the pay rate of the instructor.'))
    availableForPrivates = models.BooleanField(_('Available For private lessons'),default=True,help_text=_('Check this box if you would like to be listed as available for private lessons from students.'))

    @property
    def assistant(self):
        return self.status == self.InstructorStatus.assistant
    assistant.fget.short_description = _('Is assistant')

    @property
    def guest(self):
        return self.status == self.InstructorStatus.guest
    guest.fget.short_description = _('Is guest')

    @property
    def retired(self):
        return self.status == self.InstructorStatus.retired
    retired.fget.short_description = _('Is retired')

    @property
    def hide(self):
        return self.status == self.InstructorStatus.hidden
    retired.fget.short_description = _('Is hidden')

    @property
    def activeGuest(self):
        return (
            self.status == self.InstructorStatus.guest and
            self.activeUpcoming
        )
    retired.fget.short_description = _('Is upcoming guest')

    @property
    def statusLabel(self):
        return self.InstructorStatus.values.get(self.status,'')
    statusLabel.fget.short_description = _('Status')

    class Meta:
        verbose_name = _('Instructor')
        verbose_name_plural = _('Instructors')
        permissions = (
            ('update_instructor_bio',_('Can update instructors\' bio information')),
            ('view_own_instructor_stats',_('Can view one\'s own statistics (if an instructor)')),
            ('view_other_instructor_stats',_('Can view other instructors\' statistics')),
            ('view_own_instructor_finances',_('Can view one\'s own financial/payment data (if an instructor)')),
            ('view_other_instructor_finances',_('Can view other instructors\' financial/payment data')),
        )


class ClassDescription(models.Model):
    '''
    All the classes we teach.
    '''
    title = models.CharField(_('Title'),max_length=200)
    description = HTMLField(_('Description'),blank=True)
    shortDescription = models.TextField(_('Short description'),blank=True,help_text=_('May be used for tag lines and feeds.'))
    danceTypeLevel = models.ForeignKey(DanceTypeLevel,verbose_name=_('Dance Type & Level'),default=1,on_delete=models.SET_DEFAULT)

    slug = models.SlugField(_('Slug'),max_length=100,unique=True,blank='True',help_text=_('This is used in the URL for the individual class pages.  You can override the default'))

    oneTimeSeries = models.BooleanField(_('One Time Series'),default=False,help_text=_('If checked, this class description will not show up in the dropdown menu when creating a new series.'))

    @property
    def danceTypeName(self):
        return self.danceTypeLevel.danceType.name
    danceTypeName.fget.short_description = _('Dance type')

    @property
    def levelName(self):
        return self.danceTypeLevel.name
    levelName.fget.short_description = _('Level')

    @property
    def lastOffered(self):
        '''
        Returns the start time of the last time this series was offered
        '''
        return self.event_set.order_by('-startTime').first().startTime
    lastOffered.fget.short_description = _('Last offered')

    @property
    def lastOfferedMonth(self):
        '''
        Sometimes a Series is associated with a month other than the one
        in which the first class begins, so this returns a (year,month) tuple
        that can be used in admin instead.
        '''
        lastOfferedSeries = self.event_set.order_by('-startTime').first()
        return (lastOfferedSeries.year,lastOfferedSeries.month)
    lastOfferedMonth.fget.short_description = _('Last offered')

    def __str__(self):
        return self.title

    class Meta:
        '''
        Show descriptions of classes that were most recently offered first.
        '''
        ordering = ('-series__startTime',)
        verbose_name = _('Class series description')
        verbose_name_plural = _('Class series descriptions')


class Location(models.Model):
    '''
    Events are held at locations.
    '''
    class StatusChoices(DjangoChoices):
        active = ChoiceItem('A',_('Active Location'))
        former = ChoiceItem('F',_('Former Location'))
        specialEvents = ChoiceItem('S',_('Special Event Location (not shown by default)'))

    name = models.CharField(_('Name'),max_length=80,unique=True,help_text=_('Give this location a name.'))

    address = models.CharField('Street address',max_length=50,help_text=_('Enter the location\'s street address.'),blank=True,null=True)
    city = models.CharField(_('City'),max_length=30,default='Cambridge')
    state = models.CharField(_('2-digit state code'),max_length=12,default='MA')
    zip = models.CharField(_('ZIP/postal code'), max_length=12,default='02138')

    directions = HTMLField(_('Directions'),help_text=_('Insert any detailed directions that you would like here.  Use HTML to include videos, formatting, etc.'),null=True,blank=True)

    # This property restricts the visibility of the location in dropdowns
    # and on the publicly presented list of locations
    status = models.CharField(_('Status'),max_length=1,help_text=_('Is this location used regularly, used for special events, or no longer used?'),choices=StatusChoices.choices,default=StatusChoices.active)

    orderNum = models.FloatField(_('Order number'),default=0,help_text=_('This determines the order that the locations show up on the Locations page.'))

    defaultCapacity = models.PositiveIntegerField(_('Default Venue Capacity'),null=True,blank=True,default=get_defaultEventCapacity,help_text=_('If set, this will be used to determine capacity for class series in this venue.'))

    @property
    def address_string(self):
        return self.address + ', ' + self.city + ', ' + self.state + ' ' + self.zip
    address_string.fget.short_description = _('Address')

    @property
    def jsonCalendarFeed(self):
        '''
        Allows for easy viewing of location-specific calendar feeds.
        '''
        return reverse('jsonCalendarLocationFeed', args=(self.id,))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Location')
        verbose_name_plural = _('Locations')
        ordering = ('orderNum',)


class Room(models.Model):
    '''
    Locations may have multiple rooms, each of which may have its own capacity.
    '''
    name = models.CharField(_('Name'),max_length=80,help_text=_('Give this room a name.'))
    location = models.ForeignKey(Location,verbose_name=_('Location'),on_delete=models.CASCADE)

    defaultCapacity = models.PositiveIntegerField(_('Default Venue Capacity'),null=True,blank=True,default=get_defaultEventCapacity,help_text=_('If set, this will be used to determine capacity for class series in this room.'))

    description = HTMLField(_('Description'),help_text=_('By default, only room names are listed publicly.  However, you may insert any descriptive information that you would like about this room here.'), null=True, blank=True)

    @property
    def jsonCalendarFeed(self):
        '''
        Allows for easy viewing of room-specific calendar feeds.
        '''
        return reverse('jsonCalendarLocationFeed', args=(self.location.id, self.id,))

    def __str__(self):
        return self.name

    class Meta:
        unique_together = ('location','name')
        verbose_name = _('Room')
        verbose_name_plural = _('Rooms')
        ordering = ('location__name','name',)


class PricingTier(models.Model):
    name = models.CharField(max_length=50,unique=True,help_text=_('Give this pricing tier a name (e.g. \'Default 4-week series\')'))

    # By default, prices may vary by online or door registration.
    # More sophisticated discounts, including student discounts
    # may be achieved through the discounts and vouchers apps, if enabled.
    onlinePrice = models.FloatField(_('Online price'),default=0,validators=[MinValueValidator(0)])
    doorPrice = models.FloatField(_('At-the-door price'), default=0,validators=[MinValueValidator(0)])

    dropinPrice = models.FloatField(_('Single class drop-in price'),default=0,validators=[MinValueValidator(0)],help_text=_('If students are allowed to drop in, then this price will be applied per class.'))

    expired = models.BooleanField(_('Expired'),default=False,help_text=_("If this box is checked, then this pricing tier will not show up as an option when creating new series.  Use this for old prices or custom pricing that will not be repeated."))

    def getBasePrice(self,**kwargs):
        '''
        This handles the logic of finding the correct price.  If more sophisticated
        discounting systems are needed, then this PricingTier model can be subclassed,
        or the discounts and vouchers apps can be used.
        '''
        payAtDoor = kwargs.get('payAtDoor', False)
        dropIns = kwargs.get('dropIns', 0)

        if dropIns:
            return dropIns * self.dropinPrice
        if payAtDoor:
            return self.doorPrice
        return self.onlinePrice

    # basePrice is the online registration price
    @property
    def basePrice(self):
        return self.onlinePrice
    basePrice.fget.short_description = _('Base price')

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)
        verbose_name = _('Pricing tier')
        verbose_name_plural = _('Pricing tiers')


class EventSession(models.Model):
    '''
    Event sessions can be used to group different types of events together both for
    registration purposes and for application of discounts/vouchers.  By default,
    sessions are ordered according to their start date, which is set automatically based
    on the events associated with the session.
    '''

    name = models.CharField(_('Name'),max_length=100,help_text=_('Session name will be displayed.'))
    description = models.TextField(_('Description'),null=True,blank=True,help_text=_('Add an optional description.'))
    slug = models.SlugField(
        _('Slug'),
        max_length=50,
        help_text=_('Events can be accessed by a URL based on this slug, as well as by a URL specified by month.'),
    )

    startTime = models.DateTimeField(
        _('Start Time'),
        help_text=_('This value should be populated automatically based on the first start time of any event associated with this session.'),
        null=True,blank=True,
    )
    endTime = models.DateTimeField(
        _('End Time'),
        help_text=_('This value should be populated automatically based on the last end time of any event associated with this session.'),
        null=True,blank=True,
    )

    def save(self, *args, **kwargs):
        logger.debug('Save method for EventSession called. Updating start and end times')

        # Update the start and end time variables based on associated events.
        events = self.event_set.all()
        if events:
            self.startTime = events.order_by('startTime').first().startTime
            self.endTime = events.order_by('endTime').last().endTime

        super(EventSession,self).save(*args,**kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('startTime','name')
        verbose_name = _('Event session')
        verbose_name_plural = _('Event sessions')


class EventCategory(models.Model):
    '''
    This abstract base class defines the categorization schema used for
    both public and private events.  If new Events classes are created,
    then their categorization may also inherit from this class.
    '''

    name = models.CharField(_('Name'),max_length=100,unique=True,help_text=_('Category name will be displayed.'))
    description = models.TextField(_('Description'),null=True,blank=True,help_text=_('Add an optional description.'))

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)
        verbose_name = _('Event category')
        verbose_name_plural = _('Event categories')
        abstract = True


class SeriesCategory(EventCategory):
    '''
    Categorization for class series events, inherits from EventCategory.
    '''
    slug = models.SlugField(_('Slug'),max_length=50,help_text=_('This slug is used primarily for custom templates in registration, if the category is shown separately on the registration page.  You can override the default.'))
    separateOnRegistrationPage = models.BooleanField(_('Show category separately on registration page'),default=False)

    class Meta:
        verbose_name = _('Series category')
        verbose_name_plural = _('Series categories')


class PublicEventCategory(EventCategory):
    '''
    Categorization for public events, inherits from EventCategory.
    '''
    slug = models.SlugField(_('Slug'),max_length=50,help_text=_('This slug is used primarily for custom templates in registration, if the category is shown separately on the registration page.  You can override the default.'))
    separateOnRegistrationPage = models.BooleanField(_('Show category separately on registration page'),default=False)
    displayColor = RGBColorField(_('Calendar display color'),default='#0000FF')

    class Meta:
        verbose_name = _('Public event category')
        verbose_name_plural = _('Public event categories')


class Event(EmailRecipientMixin, PolymorphicModel):
    '''
    All public and private events, including class series, inherit off of this model.
    '''
    class RegStatus(DjangoChoices):
        disabled = ChoiceItem('D',_('Registration disabled'))
        enabled = ChoiceItem('O',_('Registration enabled'))
        heldClosed = ChoiceItem('K',_('Registration held closed (override default behavior)'))
        heldOpen = ChoiceItem('H',_('Registration held open (override default)'))
        linkOnly = ChoiceItem('L',_('Registration open, but hidden from registration page and calendar (link required to register)'))
        regHidden = ChoiceItem('C',_('Hidden from registration page and registration closed, but visible on calendar.'))
        hidden = ChoiceItem('X',_('Event hidden and registration closed'))

    status = models.CharField(_('Registration status'),max_length=1,choices=RegStatus.choices,help_text=_('Set the registration status and visibility status of this event.'))
    session = models.ForeignKey(EventSession,verbose_name=_('Session'),help_text=_('Optional event sessions can be used to order events for registration.'),null=True,blank=True,on_delete=models.SET_NULL)

    # The UUID field is used for private registration links
    uuid = models.UUIDField(_('Unique link ID'), default=uuid.uuid4, editable=False)

    # Although this can be inferred from status, this field is set in the database
    # to allow simpler queryset operations
    registrationOpen = models.BooleanField(_('Registration is open'),default=False)
    closeAfterDays = models.SmallIntegerField(
        _('Registration closes days from first occurrence'),
        default=get_closeAfterDays,
        null=True,
        blank=True,
        help_text=_('Enter positive values to close after first event occurrence, and negative values to close before first event occurrence.  Leave blank to keep registration open until the event has ended entirely.'))

    created = models.DateTimeField(_('Creation date'),auto_now_add=True)
    modified = models.DateTimeField(_('Last modified date'),auto_now=True)
    submissionUser = models.ForeignKey(User,verbose_name=_('Submitted by user'),null=True,blank=True,related_name='eventsubmissions',on_delete=models.SET_NULL)

    location = models.ForeignKey(Location,verbose_name=_('Location'),null=True,blank=True,on_delete=models.SET_NULL)
    room = models.ForeignKey(Room,verbose_name=_('Room'),null=True,blank=True,on_delete=models.SET_NULL)

    capacity = models.PositiveIntegerField(_('Event capacity'),null=True,blank=True)

    # These were formerly methods that were given a property decorator, but
    # we need to store them in the DB so that we can have individual class pages
    # without lots of overhead (we would have to pull the whole set of classes
    # every time someone visited a class page) in order to determine which one was
    # /%year%/%month%/%slug%/.  These fields will not be shown in the admin but will
    # be automatically updated on model save.  They can still be called as they were
    # called before.
    month = models.PositiveSmallIntegerField(_('Month'),null=True,blank=True,validators=[MinValueValidator(1),MaxValueValidator(12)])
    year = models.SmallIntegerField(_('Year'),null=True,blank=True)
    startTime = models.DateTimeField(_('Start time (first occurrence)'),null=True,blank=True)
    endTime = models.DateTimeField(_('End time (last occurrence)'),null=True,blank=True)
    duration = models.FloatField(_('Duration in hours'),null=True,blank=True,validators=[MinValueValidator(0)])

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
    getMonthName.fget.short_description = _('Month')

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
    name.fget.short_description = _('Name')

    @property
    def description(self):
        '''
        Since other types of events (PublicEvents, class Series, etc.) are subclasses
        of this class, it is a good idea to override this method for those subclasses,
        to provide a more intuitive description.  However, defining this property at the
        event level ensures that <object>.description can always be used to access a description
        of the event.
        '''
        return ''
    description.fget.short_description = _('Description')

    @property
    def shortDescription(self):
        '''
        Since other types of events (PublicEvents, class Series, etc.) are subclasses
        of this class, it is a good idea to override this method for those subclasses,
        to provide a more intuitive description.  However, defining this property at the
        event level ensures that <object>.description can always be used to access a short
        description of the event.
        '''
        return ''
    shortDescription.fget.short_description = _('Short description')

    @property
    def organizer(self):
        '''
        Since events can be organized for registration in different ways (e.g. by month,
        by session, or the interaction of the two), this property is used to make it easy
        for templates to include necessary organizing information.  Note that this method
        has nothing to do with the sorting of any queryset in use, which still has to be
        handled elsewhere.
        '''
        rule = getConstant('registration__orgRule')

        # Default grouping is "Other", in case session, month, or weekday are not specified.
        org = {
            'name': _('Other'),
            'nameFirst': _('Other'),
            'nameSecond': '',
            'id': None,
        }

        def updateForMonth(self, org):
            ''' Function to avoid repeated code '''
            if self.month:
                org.update({
                    'name': _(month_name[self.month]),
                    'nameFirst': _(month_name[self.month]),
                    'id': 'month_%s' % self.month,
                })
            return org

        def updateForSession(self, org):
            ''' Function to avoid repeated code '''
            if self.session:
                org.update({
                    'name': self.session.name,
                    'nameFirst': self.session.name,
                    'id': self.session.pk,
                })
            return org

        if rule in ['SessionFirst', 'SessionAlphaFirst']:
            org = updateForSession(self, org)
            if not org.get('id'):
                org = updateForMonth(self, org)
        elif rule == 'Month':
            org = updateForMonth(self, org)
        elif rule in ['Session','SessionAlpha']:
            org = updateForSession(self, org)
        elif rule in ['SessionMonth','SessionAlphaMonth']:
            if self.session and self.month:
                org.update({
                    'name': _('%s: %s' % (month_name[self.month], self.session.name)),
                    'nameFirst': _(month_name[self.month]),
                    'nameSecond': _(self.session.name),
                    'id': 'month_%s_session_%s' % (self.month, self.session.pk),
                })
            elif not self.month:
                org = updateForSession(self, org)
            elif not self.session:
                org = updateForMonth(self, org)
        elif rule == 'Weekday':
            w = self.weekday
            d = day_name[w]
            if w is not None:
                org.update({
                    'name': _(d),
                    'nameFirst': _(d),
                    'id': w,
                })
        elif rule == 'MonthWeekday':
            w = self.weekday
            d = day_name[w]
            m = self.month
            mn = month_name[m]
            if w is not None and m:
                org.update({
                    'name': _('%ss in %s' % (d, mn)),
                    'nameFirst': _(mn),
                    'nameSecond': _('%ss' % d),
                    'id': 'month_%s_weekday_%s' % (m, w)
                })
        return org

    @property
    def displayColor(self):
        '''
        This property is overridden for Series, for which the display color is set by
        the dance type and level of the class.
        '''
        if hasattr(self,'category') and self.category:
            return self.category.displayColor
    displayColor.fget.short_description = _('Display color')

    @property
    def durationMinutes(self):
        ''' Convenience for templates that want to report duration in minutes '''
        return self.duration * 60
    durationMinutes.fget.short_description = _('Duration in minutes')

    def get_default_recipients(self):
        ''' Overrides EmailRecipientMixin '''
        return [x.registration.customer.email for x in self.eventregistration_set.filter(cancelled=False)]

    def get_email_context(self,**kwargs):
        ''' Overrides EmailRecipientMixin '''
        context = super(Event,self).get_email_context(**kwargs)
        context.update({
            'id': self.id,
            'name': self.__str__(),
            'title': self.name,
            'start': self.firstOccurrenceTime,
            'next': self.nextOccurrenceTime,
            'last': self.lastOccurrenceTime,
            'url': self.url,
        })
        return context

    def getBasePrice(self,**kwargs):
        '''
        This method is also generally overridden by subclasses of this class, but it is
        defined here to ensure that the method always exists when looping through events.
        '''
        return None

    # For standard subclasses, basePrice is the non-student, online registration price.
    basePrice = property(fget=getBasePrice)
    basePrice.fget.short_description = _('Base price for online registration')

    def getYearAndMonth(self):

        rule = getConstant('registration__eventMonthRule')

        class_counter = list(Counter([(x.startTime.year, x.startTime.month) for x in self.eventoccurrence_set.order_by('startTime')]).items())

        # Count occurrences by year and month, and find any months with more than one occurrence in them.  Return the
        # first of these.  If no months have more than one occurrence, return the month of the first occurrence.
        if rule == 'FirstMulti' and class_counter:
            multiclass_months = [x[0] for x in class_counter if x[1] > 1]
            all_months = [x[0] for x in class_counter]

            if multiclass_months:
                return min(multiclass_months)
            elif all_months:
                return min(all_months)
        # Return the month with the most occurrences (ties are broken in favor of earlier months)
        elif rule == 'Most' and class_counter:
            class_counter.sort(key=lambda x: (-x[1], x[0]))
            return class_counter[0][0]
        # Return the month of the last occurrence
        elif rule == 'Last' and class_counter:
            class_counter.sort(key=lambda x: x[0], reverse=True)
            return class_counter[0][0]
        # Return the month of the first occurrence
        elif rule == '1' and class_counter:
            class_counter.sort(key=lambda x: x[0])
            return class_counter[0][0]
        # Return the month of the second occurrence
        elif rule == '2' and class_counter:
            class_counter.sort(key=lambda x: x[0])
            cumulative_list = list(accumulate([x[1] for x in class_counter]))
            if max(cumulative_list) >= 2:
                return class_counter[next(x[0] for x in enumerate(cumulative_list) if x[1] >= 2)][0]
            else:
                return class_counter[len(class_counter) - 1][0]

        return (None,None)

    @property
    def numOccurrences(self):
        return self.eventoccurrence_set.count()
    numOccurrences.fget.short_description = _('# Occurrences')

    @property
    def firstOccurrence(self):
        return self.eventoccurrence_set.order_by('startTime').first()
    firstOccurrence.fget.short_description = _('First occurrence')

    @property
    def firstOccurrenceTime(self):
        if self.firstOccurrence:
            return ensure_localtime(self.firstOccurrence.startTime)
        return None
    firstOccurrenceTime.fget.short_description = _('Begins')

    @property
    def nextOccurrence(self):
        return self.eventoccurrence_set.filter(**{'startTime__gte': timezone.now()}).order_by('startTime').first()
    nextOccurrence.fget.short_description = _('Next occurrence')

    @property
    def nextOccurrenceTime(self):
        if self.nextOccurrence:
            return ensure_localtime(self.nextOccurrence.startTime)
        return None
    nextOccurrenceTime.fget.short_description = _('Next occurs')

    @property
    def lastOccurrence(self):
        return self.eventoccurrence_set.order_by('startTime').last()
    lastOccurrence.fget.short_description = _('Last occurrence')

    @property
    def lastOccurrenceTime(self):
        if self.lastOccurrence:
            return ensure_localtime(self.lastOccurrence.endTime)
        return None
    lastOccurrenceTime.fget.short_description = _('Ends')

    @property
    def weekday(self):
        return self.firstOccurrenceTime.weekday()
    weekday.fget.short_description = _('Day of week')

    @property
    def hour(self):
        return self.firstOccurrenceTime.hour
    hour.fget.short_description = _('Hour')

    @property
    def minute(self):
        return self.firstOccurrenceTime.minute
    minute.fget.short_description = _('Minute')

    @property
    def isStarted(self):
        return self.firstOccurrenceTime >= timezone.now()
    isStarted.fget.short_description = _('Has begun')

    @property
    def isCompleted(self):
        return self.lastOccurrenceTime < timezone.now()
    isCompleted.fget.short_description = _('Has ended')

    @property
    def registrationEnabled(self):
        ''' Just checks if this event ever permits/permitted registration '''
        return self.status in [self.RegStatus.enabled,self.RegStatus.heldOpen,self.RegStatus.heldClosed]
    registrationEnabled.fget.short_description = _('Registration enabled')

    @property
    def numDropIns(self, includeTemporaryRegs=False):
        count = self.eventregistration_set.filter(cancelled=False,dropIn=True).count()
        if includeTemporaryRegs:
            count += self.temporaryeventregistration_set.filter(dropIn=True).exclude(
                registration__expirationDate__lte=timezone.now()).count()
        return count
    numDropIns.fget.short_description = _('# Drop-ins')

    def getNumRegistered(self, includeTemporaryRegs=False, dateTime=None):
        '''
        Method allows the inclusion of temporary registrations, as well as exclusion of
        temporary registrations that are too new (e.g. for discounts based on the first
        X registrants, we don't want to include people who started tp register later
        than the person in question.
        '''

        count = self.eventregistration_set.filter(cancelled=False,dropIn=False).count()
        if includeTemporaryRegs:
            excludes = Q(registration__expirationDate__lte=timezone.now())
            if isinstance(dateTime,datetime):
                excludes = exclude | Q(registration__dateTime__gte=dateTime)
            count += self.temporaryeventregistration_set.filter(dropIn=False).exclude(excludes).count()
        return count

    @property
    def numRegistered(self):
        return self.getNumRegistered()
    numRegistered.fget.short_description = _('# Registered')

    @property
    def availableRoles(self):
        '''
        Returns the set of roles for this event.  Since roles are not always custom specified for
        event, this looks for the set of available roles in multiple places.  If no roles are found,
        then the method returns an empty list, in which case it can be assumed that the event's registration
        is not role-specific.
        '''
        eventRoles = self.eventrole_set.filter(capacity__gt=0)
        if eventRoles.count() > 0:
            return [x.role for x in eventRoles]
        elif isinstance(self,Series):
            return self.classDescription.danceTypeLevel.danceType.roles.all()
        return []
    availableRoles.fget.short_description = _('Applicable dance roles')

    def numRegisteredForRole(self, role, includeTemporaryRegs=False):
        '''
        Accepts a DanceRole object and returns the number of registrations of that role.
        '''
        count = self.eventregistration_set.filter(cancelled=False,dropIn=False,role=role).count()
        if includeTemporaryRegs:
            count += self.temporaryeventregistration_set.filter(dropIn=False,role=role).exclude(
                registration__expirationDate__lte=timezone.now()).count()
        return count

    @property
    def numRegisteredByRole(self):
        '''
        Return a dictionary listing registrations by all available roles (including no role)
        '''
        role_list = list(self.availableRoles) + [None,]
        return {getattr(x,'name',None):self.numRegisteredForRole(x) for x in role_list}
    numRegisteredByRole.fget.short_description = _('# Registered by role')

    def capacityForRole(self,role):
        '''
        Accepts a DanceRole object and determines the capacity for that role at this event.this
        Since roles are not always custom specified for events, this looks for the set of
        available roles in multiple places, and only returns the overall capacity of the event
        if roles are not found elsewhere.
        '''
        if isinstance(role, DanceRole):
            role_id = role.id
        else:
            role_id = role

        eventRoles = self.eventrole_set.filter(capacity__gt=0)
        if eventRoles.count() > 0 and role_id not in [x.role.id for x in eventRoles]:
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

                if availableRoles.count() > 0 and role_id not in [x.id for x in availableRoles]:
                    ''' DanceType roles specified and this is not one of them '''
                    return 0
                elif availableRoles.count() > 0 and self.capacity:
                    # Divide the total capacity by the number of roles and round up.
                    return ceil(self.capacity / availableRoles.count())
            except ObjectDoesNotExist as e:
                logger.error('Error in calculating capacity for role: %s' % e)

        # No custom roles and no danceType to get roles from, so return the overall capacity
        return self.capacity

    def soldOutForRole(self,role,includeTemporaryRegs=False):
        '''
        Accepts a DanceRole object and responds if the number of registrations for that
        role exceeds the capacity for that role at this event.
        '''
        return self.numRegisteredForRole(
            role,includeTemporaryRegs=includeTemporaryRegs) >= (self.capacityForRole(role) or 0)

    @property
    def soldOut(self):
        return self.numRegistered >= (self.capacity or 0)
    soldOut.fget.short_description = _('Sold Out')

    @property
    def url(self):
        '''
        This property is typically overwritten by each subclass.
        '''
        return None
    url.fget.short_description = _('Event URL')

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

        # If set to these codes, then registration will be open or closed
        # automatically depending on the value of closeAfterDays
        automatic_codes = [
            self.RegStatus.enabled,
            self.RegStatus.linkOnly,
        ]

        if self.status in force_closed_codes and open is True:
            open = False
            modified = True
        elif self.status in force_open_codes and open is False:
            open = True
            modified = True
        elif (
            startTime and self.status in automatic_codes and ((
                self.closeAfterDays and timezone.now() > startTime + timedelta(days=self.closeAfterDays)) or
                timezone.now() > endTime) and open is True):
                    open = False
                    modified = True
        elif startTime and self.status in automatic_codes and ((
            timezone.now() < endTime and not self.closeAfterDays) or (
                self.closeAfterDays and timezone.now() < startTime + timedelta(days=self.closeAfterDays))) and open is False:
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
        if self.status in [Event.RegStatus.enabled, Event.RegStatus.linkOnly, Event.RegStatus.heldOpen] and not self.capacity:
            raise ValidationError(_('If registration is enabled then a capacity must be set.'))
        if self.room and self.location and self.room.location != self.location:
            raise ValidationError(_('Selected room is not part of selected location.'))

    def save(self, fromUpdateRegistrationStatus=False, *args, **kwargs):
        logger.debug('Save method for Event or subclass called.')

        if fromUpdateRegistrationStatus:
            logger.debug('Avoiding duplicate call to update registration status; ready to save.')
        else:
            logger.debug('About to check registration status and update if needed.')

            if self.eventoccurrence_set.all():
                self.year = self.getYearAndMonth()[0]
                self.month = self.getYearAndMonth()[1]
                self.startTime = self.eventoccurrence_set.order_by('startTime').first().startTime
                self.endTime = self.eventoccurrence_set.order_by('endTime').last().endTime
                self.duration = sum([x.duration for x in self.eventoccurrence_set.all() if not x.cancelled])

            if self.room and not self.location:
                self.location = self.room.location

            if self.room and self.room.defaultCapacity and not self.capacity:
                self.capacity = self.room.defaultCapacity
            elif self.location and not self.capacity:
                self.capacity = self.location.defaultCapacity

            modified, open = self.updateRegistrationStatus(saveMethod=True)
            if modified:
                self.registrationOpen = open
            logger.debug('Finished checking status and ready for super call. Value is %s' % self.registrationOpen)
        super(Event,self).save(*args,**kwargs)

        # Update start time and end time for associated event session.
        if self.session:
            self.session.save()

    def __str__(self):
        return str(_('Event: %s' % self.name))

    class Meta:
        verbose_name = _('Series/Event')
        verbose_name_plural = _('All Series/Events')
        ordering = ('-startTime',)


class EventOccurrence(models.Model):
    '''
    All events have one or more occurrences.  For example, class series have classes,
    public events may be one time (one occurrence) or they may occur repeatedly.
    '''
    event = models.ForeignKey(Event,verbose_name=_('Series/Event'),on_delete=models.CASCADE)

    startTime = models.DateTimeField(_('Start Time'))
    endTime = models.DateTimeField(_('End Time'))

    cancelled = models.BooleanField(_('Cancelled'),help_text=_('Check this box to mark that the class or event was cancelled.'), default=False)

    @property
    def duration(self):
        '''
        Returns the duration, in hours, for this occurrence
        '''
        return (self.endTime - self.startTime).seconds / 3600
    duration.fget.short_description = _('Duration')

    def allDayForDate(self,this_date,timeZone=None):
        '''
        This method determines whether the occurrence lasts the entirety of
        a specified day in the specified time zone.  If no time zone is specified,
        then it uses the default time zone).  Also, give a grace period of a few
        minutes to account for issues with the way events are sometimes entered.
        '''
        if isinstance(this_date,datetime):
            d = this_date.date()
        else:
            d = this_date

        date_start = datetime(d.year,d.month,d.day)
        naive_start = self.startTime if timezone.is_naive(self.startTime) else timezone.make_naive(self.startTime, timezone=timeZone)
        naive_end = self.endTime if timezone.is_naive(self.endTime) else timezone.make_naive(self.endTime, timezone=timeZone)

        return (
            # Ensure that all comparisons are done in local time
            naive_start <= date_start and
            naive_end >= date_start + timedelta(days=1,minutes=-30)
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

    class Meta:
        verbose_name = _('Event occurrence')
        verbose_name_plural = _('Event occurrences')
        ordering = ('event','startTime')


class EventRole(models.Model):
    event = models.ForeignKey(Event,on_delete=models.CASCADE)
    role = models.ForeignKey(DanceRole,on_delete=models.CASCADE)
    capacity = models.PositiveIntegerField()

    class Meta:
        ''' Ensure each role is only listed once per event. '''
        unique_together = ('event','role')
        verbose_name = _('Event dance role')
        verbose_name_plural = _('Event dance roles')


class EventStaffCategory(models.Model):
    name = models.CharField(_('Name'),max_length=50,unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)
        verbose_name = _('Event staff category')
        verbose_name_plural = _('Event staff categories')


class EventStaffMember(models.Model):
    '''
    Events have staff members of various types.  Instructors and
    substitute teachers are defaults, which have their own proxy
    models and managers.  However, other types may be created by
    overriding StaffType.
    '''
    category = models.ForeignKey(EventStaffCategory,verbose_name=_('Category'),null=True,on_delete=models.SET_NULL)

    event = models.ForeignKey(Event,verbose_name=_('Event'),on_delete=models.CASCADE)
    occurrences = models.ManyToManyField(EventOccurrence,blank=True,verbose_name=_('Applicable event occurrences'))

    staffMember = models.ForeignKey(StaffMember,verbose_name=_('Staff Member'),on_delete=models.CASCADE)
    replacedStaffMember = models.ForeignKey('self',verbose_name=_('Replacement for'),related_name='replacementFor',null=True,blank=True,on_delete=models.SET_NULL)

    specifiedHours = models.FloatField(
        _('Number of hours (optional)'),
        help_text=_('If unspecified, then the net number of hours is based on the duration of the applicable event occurrences.'),null=True,blank=True,
        validators=[MinValueValidator(0)]
    )

    # For keeping track of who submitted and when.
    submissionUser = models.ForeignKey(User,verbose_name=_('Submission User'),null=True,on_delete=models.SET_NULL)
    creationDate = models.DateTimeField(_('Creation date'),auto_now_add=True)
    modifyDate = models.DateTimeField(_('Last modified date'),auto_now=True)

    @property
    def netHours(self):
        '''
        For regular event staff, this is the net hours worked for financial purposes.
        For Instructors, netHours is caclulated net of any substitutes.
        '''
        if self.specifiedHours is not None:
            return self.specifiedHours
        elif self.category in [getConstant('general__eventStaffCategoryAssistant'),getConstant('general__eventStaffCategoryInstructor')]:
            return self.event.duration - sum([sub.netHours for sub in self.replacementFor.all()])
        else:
            return sum([x.duration for x in self.occurrences.filter(cancelled=False)])
    netHours.fget.short_description = _('Net hours')

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

    class Meta:
        ordering = ('event', 'staffMember__lastName', 'staffMember__firstName')
        unique_together = ('staffMember','event','category','replacedStaffMember')
        verbose_name = _('Event staff member')
        verbose_name_plural = _('Event staff members')


class Series(Event):
    '''
    A series is a particular type (subclass) of event which has instructors
    (a subclass of staff).  Series are also matched to a ClassDescription,
    through which their DanceType and DanceTypeLevel are specified.
    '''

    classDescription = models.ForeignKey(ClassDescription,verbose_name=_('Class description'),null=True,on_delete=models.SET_NULL)
    category = models.ForeignKey(SeriesCategory,verbose_name=_('Series category (optional)'),null=True,blank=True,help_text=_('Custom series categories may be used to display special series (e.g. one-offs, visiting instructors) separately on your registration page.'),on_delete=models.SET_NULL)
    allowDropins = models.BooleanField(_('Allow class drop-ins'), default=False, help_text=_('If checked, then all staff will be able to register students as drop-ins.'))

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
    teachers.fget.short_description = _('Instructors')

    pricingTier = models.ForeignKey(PricingTier,verbose_name=_('Pricing tier'),on_delete=models.PROTECT)

    @property
    def name(self):
        '''
        Overrides property from Event base class.
        '''
        return getattr(getattr(self,'classDescription',None),'title','')
    name.fget.short_description = _('Name')

    @property
    def description(self):
        '''
        Overrides property from Event base class.
        '''
        return getattr(getattr(self,'classDescription',None),'description','')
    description.fget.short_description = _('Description')

    @property
    def shortDescription(self):
        '''
        Overrides property from Event base class.
        '''
        cd = getattr(self,'classDescription',None)
        if cd:
            sd = getattr(cd,'shortDescription','')
            d = getattr(cd,'description','')
            return sd if sd else d
        return ''
    shortDescription.fget.short_description = _('Short description')

    @property
    def slug(self):
        '''
        No property in the Event base class, but PublicEvents have a slug field, so this allows
        us to iterate over that property in templates
        '''
        return getattr(getattr(self,'classDescription',None),'slug','')
    slug.fget.short_description = _('Slug')

    @property
    def displayColor(self):
        '''
        Overrides property from Event base class.
        '''
        cd = getattr(self,'classDescription',None)
        if cd:
            return cd.danceTypeLevel.displayColor
    displayColor.fget.short_description = _('Calendar display color')

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
    basePrice.fget.short_description = _('Base price for online registration')

    @property
    def url(self):
        orgRule = getConstant('registration__orgRule')

        if self.status in [self.RegStatus.hidden, self.RegStatus.linkOnly]:
            return None
        elif orgRule in ['SessionFirst', 'SessionAlphaFirst', 'SessionMonth','SessionAlphaMonth'] and self.session:
            return reverse('classViewSessionMonth',args=[self.session.slug,self.year,month_name[self.month or 0] or None,self.classDescription.slug])
        elif orgRule in ['Session','SessionAlpha'] and self.session:
            return reverse('classViewSession',args=[self.session.slug,self.classDescription.slug])
        else:        
            return reverse('classView',args=[self.year,month_name[self.month or 0] or None,self.classDescription.slug])

    url.fget.short_description = _('Class series URL')

    def clean(self):
        if self.allowDropins and not self.pricingTier.dropinPrice:
            raise ValidationError(_('If drop-ins are allowed then drop-in price must be specified by the Pricing Tier.'))
        super(Series,self).clean()

    def __str__(self):
        if self.month and self.year and self.classDescription:
            # In case of unsaved series, month and year are not yet set.
            return str(_('%s %s: %s' % (month_name[self.month or 0],str(self.year),self.classDescription.title)))
        elif self.classDescription:
            return str(_('Class Series: %s' % self.classDescription.title))
        else:
            return str(_('Class Series'))

    class Meta:
        verbose_name = _('Class series')
        verbose_name_plural = _('Class series')


class SeriesTeacherManager(models.Manager):
    '''
    Limits SeriesTeacher queries to only staff reported as teachers, and ensures that
    these individuals are reported as teachers when created.
    '''

    def get_queryset(self):
        return super(SeriesTeacherManager,self).get_queryset().filter(
            category=getConstant('general__eventStaffCategoryInstructor')
        )

    def create(self, **kwargs):
        kwargs.update({
            'category': getConstant('general__eventStaffCategoryInstructor').id,
            'occurrences': kwargs.get('event').eventoccurrence_set.all(),
        })
        return super(SeriesTeacherManager,self).create(**kwargs)


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
        if self.specifiedHours is not None:
            return self.specifiedHours
        return self.event.duration - sum([sub.netHours for sub in self.replacementFor.all()])
    netHours.fget.short_description = _('Net hours taught')

    def __str__(self):
        return str(self.staffMember) + " - " + str(self.event)

    class Meta:
        proxy = True
        verbose_name = _('Series instructor')
        verbose_name_plural = _('Series instructors')


class SubstituteTeacherManager(models.Manager):
    '''
    Limits SeriesTeacher queries to only staff reported as teachers, and ensures that
    these individuals are reported as teachers when created.
    '''

    def get_queryset(self):
        return super(SubstituteTeacherManager,self).get_queryset().filter(
            category=getConstant('general__eventStaffCategorySubstitute')
        )

    def create(self, **kwargs):
        kwargs.update({
            'category': getConstant('general__eventStaffCategorySubstitute').id})
        return super(SubstituteTeacherManager,self).create(**kwargs)


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
            'month': _(month_name[self.event.month or 0]),
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
        verbose_name = _('Substitute instructor')
        verbose_name_plural = _('Substitute instructors')


class EventDJManager(models.Manager):
    '''
    Limits Dj queries to only staff reported as DJs, and ensures that
    these individuals are reported as DJs when created.
    '''

    def get_queryset(self):
        return super(EventDJManager,self).get_queryset().filter(
            category=getConstant('general__eventStaffCategoryDJ')
        )

    def create(self, **kwargs):
        kwargs.update({
            'category': getConstant('general__eventStaffCategoryDJ').id,
        })
        return super(EventDJManager,self).create(**kwargs)


class EventDJ(EventStaffMember):
    '''
    A proxy model that provides staff member properties specific to
    keeping track of series teachers.
    '''
    objects = EventDJManager()

    @property
    def netHours(self):
        '''
        For regular event staff, this is the net hours worked for financial purposes.
        For Instructors, netHours is calculated net of any substitutes.
        '''
        return self.event.duration - sum([sub.netHours for sub in self.replacementFor.all()])
    netHours.fget.short_description = _('Net hours taught')

    def __str__(self):
        return str(self.staffMember) + " - " + str(self.event)

    class Meta:
        proxy = True
        verbose_name = _('Event DJ')
        verbose_name_plural = _('Event DJs')


class PublicEvent(Event):
    '''
    Special Events which may have their own display page.
    '''

    title = models.CharField(_('Title'),max_length=100,help_text=_('Give the event a title'))
    slug = models.SlugField(_('Slug'),max_length=100,help_text=_('This is for the event page URL, you can override the default.'))

    category = models.ForeignKey(PublicEventCategory,null=True,blank=True,verbose_name=_('Category (optional)'),help_text=_('Custom event categories may be used to display special types of events (e.g. practice sessions) separately on your registration page.  They may also be displayed in different colors on the public calendar.'),on_delete=models.SET_NULL)
    descriptionField = HTMLField(_('Description'),null=True,blank=True,help_text=_('Describe the event for the event page.'))
    shortDescriptionField = models.TextField(_('Short description'),null=True,blank=True,help_text=_('Shorter description for \"taglines\" and feeds.'))
    link = models.URLField(_('External link to event (if applicable)'),blank=True,null=True,help_text=_('Optionally include the URL to a page for this Event.  If set, then the site\'s auto-generated Event page will instead redirect to this URL.'))

    # The pricing tier is optional, but registrations cannot be enabled unless a pricing tier is
    # specified (the pricing tier may specify the price as free for Free events).
    pricingTier = models.ForeignKey(PricingTier,null=True,blank=True,verbose_name=_('Pricing Tier'),on_delete=models.SET_NULL)

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
    basePrice.fget.short_description = _('Base price for online registration')

    @property
    def djs(self):
        '''
        Returns the list of DJs
        '''
        return EventDJ.objects.filter(event=self)
    djs.fget.short_description = _('DJs')

    @property
    def name(self):
        '''
        Overrides property from Event base class.
        '''
        return self.title
    name.fget.short_description = _('Name')

    @property
    def description(self):
        '''
        Overrides property from Event base class.
        '''
        return self.descriptionField
    description.fget.short_description = _('Description')

    @property
    def shortDescription(self):
        '''
        Overrides property from Event base class.
        '''
        if self.shortDescriptionField:
            return self.shortDescriptionField
        return self.descriptionField
    shortDescription.fget.short_description = _('Short description')

    @property
    def url(self):
        orgRule = getConstant('registration__orgRule')

        if self.status in [self.RegStatus.hidden, self.RegStatus.linkOnly]:
            return None
        elif orgRule in ['SessionFirst', 'SessionAlphaFirst', 'SessionMonth','SessionAlphaMonth'] and self.session:
            return reverse('eventViewSessionMonth',args=[self.session.slug,self.year,month_name[self.month or 0] or None,self.slug])
        elif orgRule in ['Session','SessionAlpha'] and self.session:
            return reverse('eventViewSession',args=[self.session.slug,self.slug])
        else:        
            return reverse('eventView',args=[self.year,month_name[self.month or 0] or None,self.slug])

    def __str__(self):
        try:
            return '%s: %s' % (self.name, getattr(self.eventoccurrence_set.first(),'startTime').strftime('%a., %B %d, %Y, %I:%M %p'))
        except AttributeError:
            # Event has no occurrences
            return self.name

    class Meta:
        verbose_name = _('Public event')
        verbose_name_plural = _('Public events')


class CustomerGroup(EmailRecipientMixin, models.Model):
    '''
    A customer group can be used to send emails and to define group-specific
    discounts and vouchers.
    '''
    name = models.CharField(_('Group name'),max_length=100)

    def memberCount(self):
        return self.customer_set.count()

    def get_default_recipients(self):
        ''' Overrides EmailRecipientMixin '''
        return [x.email for x in self.customer_set.all()]

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)
        verbose_name = _('Customer group')
        verbose_name_plural = _('Customer groups')


class Customer(EmailRecipientMixin, models.Model):
    '''
    Not all customers choose to log in when they sign up for classes, and sometimes Users register their spouses, friends,
    or other customers.  However, we still need to keep track of those customers' registrations.  So, Customer objects
    are unique for each combination of name and email address, even though Users are unique by email address only.  Customers
    also store name and email information separately from the User object.
    '''
    user = models.OneToOneField(User,null=True,blank=True,verbose_name=_('User account'),on_delete=models.SET_NULL)

    first_name = models.CharField(_('First name'), max_length=30)
    last_name = models.CharField(_('Last name'), max_length=30)
    email = models.EmailField(_('Email address'))
    phone = models.CharField(_('Telephone'),max_length=20,null=True,blank=True)

    groups = models.ManyToManyField(
        CustomerGroup,
        verbose_name=_('Customer groups'),blank=True,
        help_text=_('Customer groups may be used for group-specific discounts and vouchers, as well as for email purposes.')
    )

    # PostgreSQL can store arbitrary additional information associated with this customer
    # in a JSONfield, but to remain database agnostic we are using django-jsonfield
    data = JSONField(_('Additional data'),default={},blank=True)

    @property
    def fullName(self):
        return ' '.join([self.first_name or '',self.last_name or ''])
    fullName.fget.short_description = _('Name')

    @property
    def numEventRegistrations(self):
        return EventRegistration.objects.filter(registration__customer=self).count()
    numEventRegistrations.fget.short_description = _('# Events/series registered')

    @property
    def numClassSeries(self):
        return EventRegistration.objects.filter(registration__customer=self,event__series__isnull=False).count()
    numClassSeries.fget.short_description = _('# Series registered')

    @property
    def numPublicEvents(self):
        return EventRegistration.objects.filter(registration__customer=self,event__publicevent__isnull=False).count()
    numPublicEvents.fget.short_description = _('# Public events registered')

    @property
    def firstSeries(self):
        return EventRegistration.objects.filter(registration__customer=self,event__series__isnull=False).\
            order_by('event__startTime').first().event
    firstSeries.fget.short_description = _('Customer\'s first series')

    @property
    def firstSeriesDate(self):
        return EventRegistration.objects.filter(registration__customer=self,event__series__isnull=False).\
            order_by('event__startTime').first().event.startTime
    firstSeriesDate.fget.short_description = _('Customer\'s first series date')

    @property
    def lastSeries(self):
        return EventRegistration.objects.filter(registration__customer=self,event__series__isnull=False).\
            order_by('-event__startTime').first().event
    lastSeries.fget.short_description = _('Customer\'s most recent series')

    @property
    def lastSeriesDate(self):
        return EventRegistration.objects.filter(registration__customer=self,event__series__isnull=False).\
            order_by('-event__startTime').first().event.startTime
    lastSeriesDate.fget.short_description = _('Customer\'s most recent series date')

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

    def get_default_recipients(self):
        ''' Overrides EmailRecipientMixin '''
        return [self.email,]

    def get_email_context(self,**kwargs):
        ''' Overrides EmailRecipientMixin '''
        context = super(Customer,self).get_email_context(**kwargs)
        context.update({
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'fullName': self.fullName,
            'phone': self.phone,
        })
        return context

    def __str__(self):
        return '%s: %s' % (self.fullName, self.email)

    class Meta:
        unique_together = ('last_name','first_name','email')
        ordering = ('last_name','first_name')
        permissions = (
            ('can_autocomplete_users',_('Able to use customer and User autocomplete features (in various admin forms)')),
            ('view_other_user_profiles',_('Able to view other Customer and User profile pages')),
        )
        verbose_name = _('Customer')
        verbose_name_plural = _('Customers')


class TemporaryRegistration(EmailRecipientMixin, models.Model):
    firstName = models.CharField(_('First name'),max_length=100,null=True)
    lastName = models.CharField(_('Last name'),max_length=100,null=True)
    email = models.CharField(_('Email address'),max_length=200,null=True)
    phone = models.CharField(_('Telephone'),max_length=20,null=True,blank=True)

    howHeardAboutUs = models.TextField(_('How they heard about us'),default='',blank=True,null=True)
    student = models.BooleanField(_('Eligible for student discount'),default=False)
    payAtDoor = models.BooleanField(_('At-the-door registration'),default=False)

    submissionUser = models.ForeignKey(User, verbose_name=_('registered by user'),related_name='submittedtemporaryregistrations',null=True,blank=True,on_delete=models.SET_NULL)

    comments = models.TextField(_('Comments'),default='')
    dateTime = models.DateTimeField(_('Registration date/time'),blank=True,null=True)
    priceWithDiscount = models.FloatField(_('Price net of discounts'),null=True,validators=[MinValueValidator(0)])

    # PostgreSQL can store arbitrary additional information associated with this registration
    # in a JSONfield, but to remain database-agnostic we are using django-jsonfield.  This allows
    # hooked in registration-related procedures to hang on to miscellaneous data
    # for the duration of the registration process without having to create models in another app.
    # By default (and for security reasons), the registration system ignores any passed data that it does not
    # expect, so you will need to hook into the registration system to ensure that any extra information that
    # you want to use is not discarded.
    data = JSONField(_('Additional data'),default={},blank=True)

    expirationDate = models.DateTimeField(
        _('Expiration date'),
        help_text=_(
            'When a customer attempts to begin the registration process, the system looks for ' +
            'temporary registrations that are still in progress (with a future expiration date) ' +
            'to determine if there is space for them to register.'
        )
    )

    @property
    def fullName(self):
        return ' '.join([self.firstName or '',self.lastName or '']).strip()
    fullName.fget.short_description = _('Name')

    @property
    def seriesPrice(self):
        return self.temporaryeventregistration_set.filter(Q(event__series__isnull=False)).aggregate(Sum('price')).get('price__sum')
    seriesPrice.fget.short_description = _('Price of class series')

    @property
    def publicEventPrice(self):
        return self.temporaryeventregistration_set.filter(Q(event__publicevent__isnull=False)).aggregate(Sum('price')).get('price__sum')
    publicEventPrice.fget.short_description = _('Price of public events')

    @property
    def totalPrice(self):
        return self.temporaryeventregistration_set.aggregate(Sum('price')).get('price__sum')
    totalPrice.fget.short_description = _('Total price before discounts')

    @property
    def addTaxes(self):
        '''
        If the buyer is expected to pay sales tax, this can be used in the
        registration process to show a line item of what the taxes are.
        '''
        if getConstant('registration__buyerPaysSalesTax'):
            return self.priceWithDiscount * (getConstant('registration__salesTaxRate') or 0) / 100
        else:
            return 0

    @property
    def priceWithDiscountAndTaxes(self):
        '''
        Some payment processors don't separate out taxes as a line item, so this
        method ensures that individuals are charged the appropriate amount depending
        on whether or no we expect them to pay any taxes on their purchase.
        '''
        return self.priceWithDiscount + self.addTaxes

    @property
    def totalDiscount(self):
        return self.totalPrice - self.priceWithDiscount
    totalDiscount.fget.short_description = _('Total discounts')

    @property
    def firstStartTime(self):
        return min([x.event.startTime for x in self.temporaryeventregistration_set.all()])
    firstStartTime.fget.short_description = _('First event starts')

    @property
    def firstSeriesStartTime(self):
        return min([x.event.startTime for x in self.temporaryeventregistration_set.filter(event__series__isnull=False)])
    firstSeriesStartTime.fget.short_description = _('First class series starts')

    @property
    def lastEndTime(self):
        return max([x.event.endTime for x in self.temporaryeventregistration_set.all()])
    lastEndTime.fget.short_description = _('Last event ends')

    @property
    def lastSeriesEndTime(self):
        return max([x.event.endTime for x in self.temporaryeventregistration_set.filter(event__series__isnull=False)])
    lastSeriesEndTime.fget.short_description = _('Last class series ends')

    def getTimeOfClassesRemaining(self,numClasses=0):
        '''
        For checking things like prerequisites, it's useful to check if a requirement is 'almost' met
        '''
        occurrences = EventOccurrence.objects.filter(
            cancelled=False,
            event__in=[x.event for x in self.temporaryeventregistration_set.filter(event__series__isnull=False)],
        ).order_by('-endTime')
        if occurrences.count() > numClasses:
            return occurrences[numClasses].endTime
        else:
            return occurrences.last().startTime

    def get_default_recipients(self):
        ''' Overrides EmailRecipientMixin '''
        return [self.email,]

    def get_email_context(self,**kwargs):
        ''' Overrides EmailRecipientMixin '''
        context = super(TemporaryRegistration,self).get_email_context(**kwargs)
        context.update({
            'first_name': self.firstName,
            'last_name': self.lastName,
            'registrationComments': self.comments,
            'registrationHowHeardAboutUs': self.howHeardAboutUs,
            'eventList': [x.get_email_context(includeName=False) for x in self.temporaryeventregistration_set.all()],
        })

        if hasattr(self,'invoice') and self.invoice:
            context.update({
                'invoice': self.invoice.get_email_context(),
            })

        return context

    def finalize(self,**kwargs):
        '''
        This method is called when the payment process has been completed and a registration
        is ready to be finalized.  It also fires the post-registration signal
        '''
        dateTime = kwargs.pop('dateTime', timezone.now())

        # If sendEmail is passed as False, then we won't send an email
        sendEmail = kwargs.pop('sendEmail', True)

        customer, created = Customer.objects.update_or_create(
            first_name=self.firstName,last_name=self.lastName,
            email=self.email,defaults={'phone': self.phone}
        )

        regArgs = {
            'customer': customer,
            'firstName': self.firstName,
            'lastName': self.lastName,
            'dateTime': dateTime,
            'temporaryRegistration': self
        }
        for key in ['comments', 'howHeardAboutUs', 'student', 'priceWithDiscount','payAtDoor']:
            regArgs[key] = kwargs.pop(key, getattr(self,key,None))

        # All other passed kwargs are put into the data JSON
        regArgs['data'] = self.data
        regArgs['data'].update(kwargs)

        realreg = Registration(**regArgs)
        realreg.save()
        logger.debug('Created registration with id: ' + str(realreg.id))

        for er in self.temporaryeventregistration_set.all():
            logger.debug('Creating eventreg for event: ' + str(er.event.id))
            realer = EventRegistration(registration=realreg,event=er.event,
                                       customer=customer,role=er.role,
                                       price=er.price,
                                       dropIn=er.dropIn,
                                       data=er.data
                                       )
            realer.save()

        # Mark this temporary registration as expired, so that it won't
        # be counted twice against the number of in-progress registrations
        # in the future when another customer tries to register.
        self.expirationDate = timezone.now()
        self.save()

        # This signal can, for example, be caught by the vouchers app to keep track of any vouchers
        # that were applied
        post_registration.send(
            sender=TemporaryRegistration,
            registration=realreg
        )

        if sendEmail:
            if getConstant('email__disableSiteEmails'):
                logger.info('Sending of confirmation emails is disabled.')
            else:
                logger.info('Sending confirmation email.')
                template = getConstant('email__registrationSuccessTemplate')

                realreg.email_recipient(
                    subject=template.subject,
                    content=template.content,
                    html_content=template.html_content,
                    send_html=template.send_html,
                    from_address=template.defaultFromAddress,
                    from_name=template.defaultFromName,
                    cc=template.defaultCC,
                )

        # Return the newly-created finalized registration object
        return realreg

    def __str__(self):
        if self.fullName:
            return '%s #%s: %s' % (_('Temporary Registration'), self.id, self.fullName)
        else:
            return '%s #%s' % (_('Temporary Registration'), self.id)

    class Meta:
        ordering = ('-dateTime',)
        verbose_name = _('Temporary registration')
        verbose_name_plural = _('Temporary registrations')


class Registration(EmailRecipientMixin, models.Model):
    '''
    There is a single registration for an online transaction.
    A single Registration includes multiple classes, as well as events.
    '''
    firstName = models.CharField(_('First name'),max_length=100,default='TBD')
    lastName = models.CharField(_('Last name'),max_length=100,default='TBD')
    customer = models.ForeignKey(Customer,verbose_name=_('Customer'),on_delete=models.CASCADE)

    howHeardAboutUs = models.TextField(_('How they heard about us'),default='',blank=True,null=True)
    student = models.BooleanField(_('Eligible for student discount'),default=False)
    payAtDoor = models.BooleanField(_('At-the-door registration'),default=False)

    priceWithDiscount = models.FloatField(verbose_name=_('Price net of discounts'),validators=[MinValueValidator(0)])
    comments = models.TextField(_('Comments'),default='',blank=True,null=True)

    temporaryRegistration = models.OneToOneField(
        TemporaryRegistration,null=True,
        verbose_name=_('Associated temporary registration'),on_delete=models.SET_NULL
    )
    dateTime = models.DateTimeField(blank=True,null=True,verbose_name=_('Registration date/time'))

    # PostgreSQL can store arbitrary additional information associated with this registration
    # in a JSONfield, but to remain database-agnostic we are using django-jsonfield
    data = JSONField(_('Additional data'),default={},blank=True)

    @property
    def warningFlag(self):
        '''
        When viewing individual event registrations, there are a large number of potential
        issues that can arise that may warrant scrutiny. This property just checks all of
        these conditions and indicates if anything is amiss so that the template need not
        check each of these conditions individually repeatedly.
        '''
        if not hasattr(self,'invoice'):
            return True
        if apps.is_installed('danceschool.financial'):
            '''
            If the financial app is installed, then we can also check additional
            properties set by that app to ensure that there are no inconsistencies
            '''
            if self.invoice.revenueNotYetReceived != 0 or self.invoice.revenueMismatch:
                return True
        return (
            self.priceWithDiscount != self.invoice.total or
            self.invoice.unpaid or self.invoice.outstandingBalance != 0
        )
    warningFlag.fget.short_description = _('Issue with event registration')

    @property
    def refundFlag(self):
        if (
            not hasattr(self,'invoice') or
            self.invoice.adjustments != 0 or
            (apps.is_installed('danceschool.financial') and self.invoice.revenueRefundsReported != 0)
        ):
            return True
        return False
    refundFlag.fget.short_description = _('Transaction was partially refunded')

    @property
    def fullName(self):
        return self.customer.fullName
    fullName.fget.short_description = _('Name')

    @property
    def email(self):
        '''
        This exists so that the Invoice views can always find an email for either
        registrations or temporary registrations without requiring separate logic
        for each class.
        '''
        return self.customer.email
    email.fget.short_description = _('Email address')

    @property
    def seriesPrice(self):
        return self.eventregistration_set.filter(Q(event__series__isnull=False)).aggregate(Sum('price')).get('price__sum') or 0
    seriesPrice.fget.short_description = _('Price of class series')

    @property
    def publicEventPrice(self):
        return self.eventregistration_set.filter(Q(event__publicevent__isnull=False)).aggregate(Sum('price')).get('price__sum') or 0
    publicEventPrice.fget.short_description = _('Price of public events')

    @property
    def totalPrice(self):
        return self.eventregistration_set.aggregate(Sum('price')).get('price__sum')
    totalPrice.fget.short_description = _('Total price before discounts')

    # This alias just makes it easier to register properties in other apps.
    @property
    def netPrice(self):
        return self.priceWithDiscount
    netPrice.fget.short_description = _('Net price')

    @property
    def addTaxes(self):
        '''
        If the buyer is expected to pay sales tax, this can be used in the
        registration process to show a line item of what the taxes are.
        '''
        if getConstant('registration__buyerPaysSalesTax'):
            return self.priceWithDiscount * (getConstant('registration__salesTaxRate') or 0) / 100
        else:
            return 0

    @property
    def priceWithDiscountAndTaxes(self):
        '''
        Some payment processors don't separate out taxes as a line item, so this
        method ensures that individuals are charged the appropriate amount depending
        on whether or no we expect them to pay any taxes on their purchase.
        '''
        return self.priceWithDiscount + self.addTaxes

    @property
    def discounted(self):
        return (self.totalPrice != self.priceWithDiscount)
    discounted.fget.short_description = _('Is discounted')

    # For now, revenue is allocated proportionately between series and events
    # as a percentage of the discounted total amount paid.  Ideally, revenue would
    # be allocated by applying discounts proportionately only to the items for which
    # they apply.  However, this has not been implemented.
    @property
    def seriesNetPrice(self):
        if self.totalPrice == 0:
            return 0
        return self.priceWithDiscount * (self.seriesPrice / self.totalPrice)
    seriesNetPrice.fget.short_description = _('Net price of class series')

    @property
    def eventNetPrice(self):
        if self.totalPrice == 0:
            return 0
        return self.priceWithDiscount * (self.publicEventPrice / self.totalPrice)
    eventNetPrice.fget.short_description = _('Net price of public events')

    @property
    def firstStartTime(self):
        return min([x.event.startTime for x in self.eventregistration_set.all()])
    firstStartTime.fget.short_description = _('First event starts')

    @property
    def firstSeriesStartTime(self):
        return min([x.event.startTime for x in self.eventregistration_set.filter(event__series__isnull=False)])
    firstSeriesStartTime.fget.short_description = _('First class series starts')

    @property
    def lastEndTime(self):
        return max([x.event.endTime for x in self.eventregistration_set.all()])
    lastEndTime.fget.short_description = _('Last event ends')

    @property
    def lastSeriesEndTime(self):
        return max([x.event.endTime for x in self.eventregistration_set.filter(event__series__isnull=False)])
    lastSeriesEndTime.fget.short_description = _('Last class series ends')

    def getTimeOfClassesRemaining(self,numClasses=0):
        '''
        For checking things like prerequisites, it's useful to check if a requirement is 'almost' met
        '''
        occurrences = EventOccurrence.objects.filter(
            cancelled=False,
            event__in=[x.event for x in self.eventregistration_set.filter(event__series__isnull=False)],
        ).order_by('-endTime')
        if occurrences.count() > numClasses:
            return occurrences[numClasses].endTime
        else:
            return occurrences.last().startTime

    def getSeriesPriceForMonth(self,dateOfInterest):
        # get all series associated with this registration
        return sum([x.price for x in self.eventregistration_set.filter(series__year=dateOfInterest.year,series__month=dateOfInterest.month).filter(Q(event__series__isnull=False))])

    def getEventPriceForMonth(self,dateOfInterest):
        # get all series associated with this registration
        return sum([x.price for x in self.eventregistration_set.filter(series__year=dateOfInterest.year,series__month=dateOfInterest.month).filter(Q(event__publicevent__isnull=False))])

    def getPriceForMonth(self,dateOfInterest):
        return sum([x.price for x in self.eventregistration_set.filter(series__year=dateOfInterest.year,series__month=dateOfInterest.month)])

    def get_default_recipients(self):
        ''' Overrides EmailRecipientMixin '''
        return [self.customer.email,]

    def get_email_context(self,**kwargs):
        ''' Overrides EmailRecipientMixin '''
        context = super(Registration,self).get_email_context(**kwargs)
        context.update({
            'first_name': self.customer.first_name,
            'last_name': self.customer.last_name,
            'registrationComments': self.comments,
            'registrationHowHeardAboutUs': self.howHeardAboutUs,
            'eventList': [x.get_email_context(includeName=False) for x in self.eventregistration_set.all()],
        })

        if hasattr(self,'invoice') and self.invoice:
            context.update({
                'invoice': self.invoice.get_email_context(),
            })

        return context

    def __str__(self):
        if self.dateTime:
            return '%s #%s: %s, %s' % (_('Registration'), self.id, self.customer.fullName, self.dateTime.strftime('%b. %Y'))
        else:
            return '%s #%s: %s' % (_('Registration'), self.id, self.customer.fullName)

    class Meta:
        ordering = ('-dateTime',)
        verbose_name = _('Registration')
        verbose_name_plural = _('Registrations')

        permissions = (
            ('view_registration_summary',_('Can access the series-level registration summary view')),
            ('checkin_customers',_('Can check-in customers using the summary view')),
            ('accept_door_payments',_('Can process door payments in the registration system')),
            ('register_dropins',_('Can register students for drop-ins.')),
            ('override_register_closed',_('Can register students for series/events that are closed for registration by the public')),
            ('override_register_soldout',_('Can register students for series/events that are officially sold out')),
            ('override_register_dropins',_('Can register students for drop-ins even if the series does not allow drop-in registration.')),
        )


class EventRegistration(EmailRecipientMixin, models.Model):
    '''
    An EventRegistration is associated with a Registration and records
    a registration for a single event.
    '''
    registration = models.ForeignKey(Registration,verbose_name=_('Registration'),on_delete=models.CASCADE)
    event = models.ForeignKey(Event,verbose_name=_('Event'),on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer,verbose_name=_('Customer'),on_delete=models.CASCADE)
    role = models.ForeignKey(DanceRole, null=True,blank=True,verbose_name=_('Dance role'),on_delete=models.SET_NULL)
    price = models.FloatField(_('Price before discounts'),default=0,validators=[MinValueValidator(0)])

    checkedIn = models.BooleanField(_('Checked In'),default=False,help_text=_('Check to mark the individual as checked in.'))

    dropIn = models.BooleanField(_('Drop-in registration'),default=False,help_text=_('If true, this is a drop-in registration.'))
    cancelled = models.BooleanField(_('Cancelled'),default=False,help_text=_('Mark as cancelled so that this registration is not counted in student/attendee counts.'))

    # PostgreSQL can store arbitrary additional information associated with this registration
    # in a JSONfield, but to remain database-agnostic we are using django-jsonfield
    data = JSONField(_('Additional data'),default={},blank=True)

    @property
    def netPrice(self):
        if self.registration.totalPrice == 0:
            return 0
        return self.price * (self.registration.netPrice / self.registration.totalPrice)
    netPrice.fget.short_description = _('Net price')

    @property
    def discounted(self):
        return (self.price != self.netPrice)
    discounted.fget.short_description = _('Is discounted')

    @property
    def matchingTemporaryRegistration(self):
        return self.registration.temporaryRegistration.temporaryeventregistration_set.get(event=self.event)
    matchingTemporaryRegistration.fget.short_description = _('Matching temporary registration')

    @property
    def warningFlag(self):
        '''
        When viewing individual event registrations, there are a large number of potential
        issues that can arise that may warrant scrutiny. This property just checks all of
        these conditions and indicates if anything is amiss so that the template need not
        check each of these conditions individually repeatedly.
        '''
        if not hasattr(self,'invoiceitem'):
            return True
        if apps.is_installed('danceschool.financial'):
            '''
            If the financial app is installed, then we can also check additional
            properties set by that app to ensure that there are no inconsistencies
            '''
            if self.invoiceitem.revenueNotYetReceived != 0 or self.invoiceitem.revenueMismatch:
                return True
        return (
            self.price != self.invoiceitem.grossTotal or
            self.invoiceitem.invoice.unpaid or self.invoiceitem.invoice.outstandingBalance != 0
        )
    warningFlag.fget.short_description = _('Issue with event registration')

    @property
    def refundFlag(self):
        if (
            not hasattr(self,'invoiceitem') or
            self.invoiceitem.invoice.adjustments != 0 or
            (apps.is_installed('danceschool.financial') and self.invoiceitem.revenueRefundsReported != 0)
        ):
            return True
        return False
    refundFlag.fget.short_description = _('Transaction was partially refunded')

    def get_default_recipients(self):
        ''' Overrides EmailRecipientMixin '''
        return [self.registration.customer.email,]

    def get_email_context(self,**kwargs):
        ''' Overrides EmailRecipientMixin '''
        includeName = kwargs.pop('includeName',True)
        context = super(EventRegistration,self).get_email_context(**kwargs)
        context.update({
            'title': self.event.name,
            'start': self.event.firstOccurrenceTime,
            'end': self.event.lastOccurrenceTime,
        })

        if includeName:
            context.update({
                'first_name': self.registration.customer.first_name,
                'last_name': self.registration.customer.last_name,
            })
        return context

    def __str__(self):
        return str(self.customer) + " " + str(self.event)

    class Meta:
        unique_together = ['registration', 'event']
        verbose_name = _('Event registration')
        verbose_name_plural = _('Event registrations')


class TemporaryEventRegistration(EmailRecipientMixin, models.Model):
    price = models.FloatField(_('Price before discounts'),validators=[MinValueValidator(0)])
    event = models.ForeignKey(Event,verbose_name=_('Event'),on_delete=models.CASCADE)
    role = models.ForeignKey(DanceRole,null=True,blank=True,verbose_name=_('Dance role'),on_delete=models.SET_NULL)
    dropIn = models.BooleanField(_('Drop-in registration'),default=False,help_text=_('If true, this is a drop-in registration.'))

    registration = models.ForeignKey(
        TemporaryRegistration,verbose_name=_('Associated temporary registration'),on_delete=models.CASCADE
    )

    # PostgreSQL can store arbitrary additional information associated with this registration
    # in a JSONfield, but to remain database-agnostic we are using django-jsonfield
    data = JSONField(_('Additional data'),default={},blank=True)

    def get_default_recipients(self):
        ''' Overrides EmailRecipientMixin '''
        return [self.registration.customer.email,]

    def get_email_context(self,**kwargs):
        ''' Overrides EmailRecipientMixin '''

        includeName = kwargs.pop('includeName',True)
        context = super(TemporaryEventRegistration,self).get_email_context(**kwargs)

        context.update({
            'title': self.event.name,
            'start': self.event.firstOccurrenceTime,
            'end': self.event.lastOccurrenceTime,
        })

        if includeName:
            context.update({
                'first_name': self.registration.firstName,
                'last_name': self.registration.lastName,
            })
        return context

    class Meta:
        unique_together = ['registration', 'event']
        verbose_name = _('Temporary event registration')
        verbose_name_plural = _('Temporary event registrations')


class EmailTemplate(models.Model):
    name = models.CharField(_('Template name'),max_length=100,unique=True)
    subject = models.CharField(_('Subject line'),max_length=200,null=True,blank=True)

    RICH_TEXT_CHOICES = (('plain',_('Plain text email')),('HTML',_('HTML rich text email')))

    richTextChoice = models.CharField(_('Send this email as'),max_length=5,choices=RICH_TEXT_CHOICES,default='plain')

    content = models.TextField(_('Plain text Content'),null=True,blank=True,help_text=_('See the list of available variables for details on what information can be included with template tags.'))
    html_content = HTMLField(_('HTML rich text content'),null=True,blank=True,help_text=_('Emails are sent as plain text by default.  To send an HTML email instead, enter your desired content in this field.'))

    defaultFromName = models.CharField(_('From name (default)'),max_length=100,null=True,blank=True,default=get_defaultEmailName)
    defaultFromAddress = models.EmailField(_('From address (default)'),max_length=100,null=True,blank=True,default=get_defaultEmailFrom)
    defaultCC = models.CharField(_('CC (default)'),max_length=100,null=True,blank=True)

    groupRequired = models.ForeignKey(Group,verbose_name=_('Group permissions required to use.'),null=True,blank=True,help_text=_('Some templates should only be visible to some users.'),on_delete=models.SET_NULL)
    hideFromForm = models.BooleanField(_('Hide from \'Email Students\' form'),default=False,help_text=_('Check this box for templates that are used for automated emails.'))

    @property
    def send_html(self):
        return (self.richTextChoice == 'HTML')
    send_html.fget.short_description = _('HTML Email Template')

    def save(self, *args, **kwargs):
        '''
        If this is an HTML template, then set the non-HTML content to be the stripped version of the HTML.
        If this is a plain text template, then set the HTML content to be null.
        '''
        if self.send_html:
            self.content = get_text_for_html(self.html_content)
        else:
            self.html_content = None

        super(EmailTemplate, self).save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)
        verbose_name = _('Email template')
        verbose_name_plural = _('Email templates')
        permissions = (
            ('send_email',_('Can send emails using the SendEmailView')),
        )


class Invoice(EmailRecipientMixin, models.Model):

    class PaymentStatus(DjangoChoices):
        unpaid = ChoiceItem('U',_('Unpaid'))
        authorized = ChoiceItem('A',_('Authorized using payment processor'))
        paid = ChoiceItem('P',_('Paid'))
        needsCollection = ChoiceItem('N',_('Cash payment recorded'))
        fullRefund = ChoiceItem('R',_('Refunded in full'))
        cancelled = ChoiceItem('C',_('Cancelled'))
        rejected = ChoiceItem('X',_('Rejected in processing'))
        error = ChoiceItem('E',_('Error in processing'))

    # The UUID field is the unique internal identifier used for this Invoice.
    # The validationString field is used only so that non-logged in users can view
    # an invoice.
    id = models.UUIDField(_('Invoice number'),primary_key=True, default=uuid.uuid4, editable=False)
    validationString = models.CharField(_('Validation string'),max_length=25,default=get_validationString,editable=False)

    # Invoices do not require that a recipient is specified, but doing so ensures
    # that invoice notifications can be sent.
    firstName = models.CharField(_('Recipient first name'),max_length=100,null=True,blank=True)
    lastName = models.CharField(_('Recipient last name'),max_length=100,null=True,blank=True)
    email = models.CharField(_('Recipient email address'),max_length=200,null=True,blank=True)

    temporaryRegistration = models.OneToOneField(
        TemporaryRegistration,verbose_name=_('Temporary registration'),null=True,blank=True,
        on_delete=models.SET_NULL,
    )
    finalRegistration = models.OneToOneField(Registration,verbose_name=_('Registration'),null=True,blank=True,on_delete=models.SET_NULL)

    creationDate = models.DateTimeField(_('Invoice created'),auto_now_add=True)
    modifiedDate = models.DateTimeField(_('Last modified'),auto_now=True)

    status = models.CharField(_('Payment status'), max_length=1, choices=PaymentStatus.choices,default=PaymentStatus.unpaid)

    paidOnline = models.BooleanField(_('Paid Online'),default=False)
    submissionUser = models.ForeignKey(User,null=True,blank=True,verbose_name=_('Registered by user'),related_name='submittedinvoices',on_delete=models.SET_NULL)
    collectedByUser = models.ForeignKey(User,null=True,blank=True,verbose_name=_('Collected by user'),related_name='collectedinvoices',on_delete=models.SET_NULL)

    grossTotal = models.FloatField(_('Total before discounts'),validators=[MinValueValidator(0)],default=0)
    total = models.FloatField(_('Total billed amount'),validators=[MinValueValidator(0)], default=0)
    adjustments = models.FloatField(_('Refunds/adjustments'),default=0)
    taxes = models.FloatField(_('Taxes'),validators=[MinValueValidator(0)],default=0)
    fees = models.FloatField(_('Processing fees'), validators=[MinValueValidator(0)],default=0)
    buyerPaysSalesTax = models.BooleanField(_('Buyer pays sales tax'), default=False)

    amountPaid = models.FloatField(default=0,verbose_name=_('Net Amount Paid'),validators=[MinValueValidator(0)])

    comments = models.TextField(_('Comments'),null=True,blank=True)

    # Additional information (record of specific transactions) can go in here
    data = JSONField(_('Additional data'),blank=True,default={})

    @classmethod
    def create_from_item(cls, amount, item_description, **kwargs):
        '''
        Creates an Invoice as well as a single associated InvoiceItem
        with the passed description (for things like gift certificates)
        '''
        submissionUser = kwargs.pop('submissionUser', None)
        collectedByUser = kwargs.pop('collectedByUser', None)
        calculate_taxes = kwargs.pop('calculate_taxes', False)
        grossTotal = kwargs.pop('grossTotal',None)

        new_invoice = cls(
            grossTotal=grossTotal or amount,
            total=amount,
            submissionUser=submissionUser,
            collectedByUser=collectedByUser,
            buyerPaysSalesTax=getConstant('registration__buyerPaysSalesTax'),
            data=kwargs,
        )

        if calculate_taxes:
            new_invoice.calculateTaxes()

        new_invoice.save()

        InvoiceItem.objects.create(
            invoice=new_invoice,
            grossTotal=grossTotal or amount,
            total=amount,
            taxes=new_invoice.taxes,
            description=item_description,
        )
        return new_invoice

    @classmethod
    def get_or_create_from_registration(cls, reg, **kwargs):

        # Return the existing Invoice if it exists
        if hasattr(reg,'invoice') and reg.invoice:
            return reg.invoice

        # Otherwise, create a new Invoice
        return cls.create_from_registration(reg,**kwargs)

    @classmethod
    def create_from_registration(cls, reg, **kwargs):
        '''
        Handles the creation of an Invoice as well as one InvoiceItem per
        assodciated TemporaryEventRegistration or registration.  Also handles taxes
        appropriately.
        '''
        submissionUser = kwargs.pop('submissionUser', None)
        collectedByUser = kwargs.pop('collectedByUser', None)
        status = kwargs.pop('status',Invoice.PaymentStatus.unpaid)

        new_invoice = cls(
            firstName=reg.firstName,
            lastName=reg.lastName,
            email=reg.email,
            grossTotal=reg.totalPrice,
            total=reg.priceWithDiscount,
            submissionUser=submissionUser,
            collectedByUser=collectedByUser,
            buyerPaysSalesTax=getConstant('registration__buyerPaysSalesTax'),
            status=status,
            data=kwargs,
        )

        if isinstance(reg, Registration):
            new_invoice.finalRegistration = reg
            ter_set = reg.eventregistration_set.all()
        elif isinstance(reg, TemporaryRegistration):
            new_invoice.temporaryRegistration = reg
            ter_set = reg.temporaryeventregistration_set.all()
        else:
            raise ValueError('Object passed is not a registration.')

        new_invoice.calculateTaxes()
        new_invoice.save()

        # Now, create InvoiceItem records for each EventRegistration
        for ter in ter_set:
            # Discounts and vouchers are always applied equally to all items at initial
            # invoice creation.
            item_kwargs = {
                'invoice': new_invoice,
                'grossTotal': ter.price,
            }

            if new_invoice.grossTotal > 0:
                item_kwargs.update({
                    'total': ter.price * (new_invoice.total / new_invoice.grossTotal),
                    'taxes': new_invoice.taxes * (ter.price / new_invoice.grossTotal),
                    'fees': new_invoice.fees * (ter.price / new_invoice.grossTotal),
                })
            else:
                item_kwargs.update({
                    'total': ter.price,
                    'taxes': new_invoice.taxes,
                    'fees': new_invoice.fees,
                })

            if isinstance(ter,TemporaryEventRegistration):
                item_kwargs['temporaryEventRegistration'] = ter
            elif isinstance(ter,EventRegistration):
                item_kwargs['finalEventRegistration'] = ter

            this_item = InvoiceItem(**item_kwargs)
            this_item.save()

        return new_invoice

    @property
    def unpaid(self):
        return (self.status != self.PaymentStatus.paid)
    unpaid.fget.short_description = _('Unpaid')

    @property
    def outstandingBalance(self):
        balance = self.total + self.adjustments - self.amountPaid
        if self.buyerPaysSalesTax:
            balance += self.taxes
        return round(balance,2)
    outstandingBalance.fget.short_description = _('Outstanding balance')

    @property
    def refunds(self):
        return -1 * self.adjustments
    refunds.fget.short_description = _('Amount refunded')

    @property
    def unallocatedAdjustments(self):
        return self.adjustments - sum([x.adjustments for x in self.invoiceitem_set.all()])
    unallocatedAdjustments.fget.short_description = _('Unallocated adjustments')

    @property
    def refundsAllocated(self):
        return (self.unallocatedAdjustments == 0)
    refundsAllocated.fget.short_description = _('All refunds are allocated')

    @property
    def netRevenue(self):
        net = self.total - self.fees + self.adjustments
        if not self.buyerPaysSalesTax:
            net -= self.taxes
        return net
    netRevenue.fget.short_description = _('Net revenue')

    @property
    def discounted(self):
        return (self.total != self.grossTotal)
    discounted.fget.short_description = _('Is discounted')

    @property
    def discountPercentage(self):
        return 1 - (self.total / self.grossTotal)
    discountPercentage.fget.short_description = _('Discount percentage')

    @property
    def statusLabel(self):
        return self.PaymentStatus.values.get(self.status,'')
    statusLabel.fget.short_description = _('Status')

    @property
    def url(self):
        '''
        Because invoice URLs are generally emailed, this
        includes the default site URL and the protocol specified in
        settings.
        '''
        if self.id:
            return '%s://%s%s' % (
                getConstant('email__linkProtocol'),
                Site.objects.get_current().domain,
                reverse('viewInvoice', args=[self.id,]),
            )
    url.fget.short_description = _('Invoice URL')

    def get_absolute_url(self):
        '''
        For adding 'View on Site' links to the admin
        '''
        return reverse('viewInvoice', args=[self.id,])

    def get_default_recipients(self):
        ''' Overrides EmailRecipientMixin '''
        if self.email:
            return [self.email,]
        if self.finalRegistration:
            return [self.finalRegistration.customer.email,]
        elif self.temporaryRegistration:
            return [self.temporaryRegistration.email,]
        return []

    def get_email_context(self,**kwargs):
        ''' Overrides EmailRecipientMixin '''
        context = super(Invoice,self).get_email_context(**kwargs)
        context.update({
            'id': self.id,
            'url': '%s?v=%s' % (self.url, self.validationString),
            'amountPaid': self.amountPaid,
            'outstandingBalance': self.outstandingBalance,
            'status': self.statusLabel,
            'creationDate': self.creationDate,
            'modifiedDate': self.modifiedDate,
            'paidOnline': self.paidOnline,
            'grossTotal': self.grossTotal,
            'total': self.total,
            'adjustments': self.adjustments,
            'taxes': self.taxes,
            'fees': self.fees,
            'comments': self.comments,
        })
        return context

    def get_payments(self):
        '''
        Since there may be many payment processors, this method simplifies the process of getting
        the list of payments
        '''
        return self.paymentrecord_set.order_by('creationDate')

    def get_payment_method(self):
        '''
        Since there may be many payment processors, this just gets the reported payment
        method name for the first payment method used.
        '''
        payments = self.get_payments()
        if payments:
            return payments.first().methodName

    def calculateTaxes(self):
        '''
        Updates the tax field to reflect the amount of taxes depending on
        the local rate as well as whether the buyer or seller pays sales tax.
        '''

        tax_rate = (getConstant('registration__salesTaxRate') or 0) / 100

        if tax_rate > 0:
            if self.buyerPaysSalesTax:
                # If the buyer pays taxes, then taxes are just added as a fraction of the price
                self.taxes = self.total * tax_rate
            else:
                # If the seller pays sales taxes, then adjusted_total will be their net revenue,
                # and under this calculation adjusted_total + taxes = the price charged
                adjusted_total = self.total / (1 + tax_rate)
                self.taxes = adjusted_total * tax_rate

    def processPayment(self, amount, fees, paidOnline=True, methodName=None, methodTxn=None, submissionUser=None, collectedByUser=None, forceFinalize=False, status=None, notify=None):
        '''
        When a payment processor makes a successful payment against an invoice, it can call this method
        which handles status updates, the creation of a final registration object (if applicable), and
        the firing of appropriate registration-related signals.
        '''
        epsilon = .01

        paymentTime = timezone.now()

        logger.info('Processing payment and creating registration objects if applicable.')

        # The payment history record is primarily for convenience, and passed values are not
        # validated.  Payment processing apps should keep individual transaction records with
        # a ForeignKey to the Invoice object.
        paymentHistory = self.data.get('paymentHistory',[])
        paymentHistory.append({
            'dateTime': paymentTime.isoformat(),
            'amount': amount,
            'fees': fees,
            'paidOnline': paidOnline,
            'methodName': methodName,
            'methodTxn': methodTxn,
            'submissionUser': getattr(submissionUser,'id',None),
            'collectedByUser': getattr(collectedByUser,'id',None),
        })
        self.data['paymentHistory'] = paymentHistory

        self.amountPaid += amount
        self.fees += fees
        self.paidOnline = paidOnline

        if submissionUser and not self.submissionUser:
            self.submissionUser = submissionUser
        if collectedByUser and not self.collectedByUser:
            self.collectedByUser = collectedByUser

        # if this completed the payment, then finalize the registration and mark
        # the invoice as Paid unless told to do otherwise.
        if forceFinalize or abs(self.outstandingBalance) < epsilon:
            self.status = status or self.PaymentStatus.paid
            if not self.finalRegistration and self.temporaryRegistration:
                self.finalRegistration = self.temporaryRegistration.finalize(dateTime=paymentTime)
            else:
                self.sendNotification(invoicePaid=True,thisPaymentAmount=amount,payerEmail=notify)
            self.save()
            if self.finalRegistration:
                for eventReg in self.finalRegistration.eventregistration_set.filter(cancelled=False):
                    # There can only be one eventreg per event in a registration, so we
                    # can filter on temporaryRegistration event to get the invoiceItem
                    # to which we should attach a finalEventRegistration
                    this_invoice_item = self.invoiceitem_set.filter(
                        temporaryEventRegistration__event=eventReg.event,
                        finalEventRegistration__isnull=True
                    ).first()
                    if this_invoice_item:
                        this_invoice_item.finalEventRegistration = eventReg
                        this_invoice_item.save()
        else:
            # The payment wasn't completed so don't finalize, but do send a notification recording the payment.
            if notify:
                self.sendNotification(invoicePaid=True,thisPaymentAmount=amount,payerEmail=notify)
            else:
                self.sendNotification(invoicePaid=True,thisPaymentAmount=amount)
            self.save()

        # If there were transaction fees, then these also need to be allocated among the InvoiceItems
        # All fees from payments are allocated proportionately.
        self.allocateFees()

    def allocateFees(self):
        '''
        Fees are allocated across invoice items based on their discounted
        total price net of adjustments as a proportion of the overall
        invoice's total price
        '''
        items = list(self.invoiceitem_set.all())

        # Check that totals and adjusments match.  If they do not, raise an error.
        if self.total != sum([x.total for x in items]):
            msg = _('Invoice item totals do not match invoice total.  Unable to allocate fees.')
            logger.error(str(msg))
            raise ValidationError(msg)
        if self.adjustments != sum([x.adjustments for x in items]):
            msg = _('Invoice item adjustments do not match invoice adjustments.  Unable to allocate fees.')
            logger.error(str(msg))
            raise ValidationError(msg)

        for item in items:
            saveFlag = False

            if self.total - self.adjustments > 0:
                item.fees = self.fees * ((item.total - item.adjustments) / (self.total - self.adjustments))
                saveFlag = True

            # In the case of full refunds, allocate fees according to the
            # initial total price of the item only.
            elif self.total - self.adjustments == 0 and self.total > 0:
                item.fees = self.fees * (item.total / self.total)
                saveFlag = True

            # In the unexpected event of fees with no total, just divide
            # the fees equally among the items.
            elif self.fees:
                item.fees = self.fees * (1 / len(items))
                saveFlag = True

            if saveFlag:
                item.save()

    def sendNotification(self, **kwargs):

        if getConstant('email__disableSiteEmails'):
            logger.info('Sending of invoice email is disabled.')
            return
        logger.info('Sending invoice notification to customer.')

        payerEmail = kwargs.pop('payerEmail','')
        amountDue = kwargs.pop('amountDue', self.outstandingBalance)

        if not payerEmail and not self.get_default_recipients():
            raise ValueError(_('Cannot send notification email because no recipient has been specified.'))

        template = getConstant('email__invoiceTemplate')

        self.email_recipient(
            subject=template.subject,
            content=template.content,
            html_content=template.html_content,
            send_html=template.send_html,
            from_address=template.defaultFromAddress,
            from_name=template.defaultFromName,
            cc=template.defaultCC,
            bcc=[payerEmail,],
            amountDue=amountDue,
            **kwargs
        )
        logger.debug('Invoice notification sent.')

    class Meta:
        ordering = ('-modifiedDate',)
        verbose_name = _('Invoice')
        verbose_name_plural = _('Invoices')
        permissions = (
            ('view_all_invoices',_('Can view invoices without passing the validation string.')),
            ('send_invoices',_('Can send invoices to students requesting payment')),
            ('process_refunds',_('Can refund customers for registrations and other invoice payments.')),
        )


class InvoiceItem(models.Model):
    '''
    Since we potentially want to facilitate financial tracking by Event and not
    just by period, we have to create a unique record for each item in each invoice.
    In the financial app (if installed), RevenueItems may link uniquely to InvoiceItems,
    and InvoiceItems may link uniquely to registration items.  Although this may seem
    like duplicated functionality, it permits the core app (as well as the payment apps)
    to operate completely independently of the financial app, making that app fully optional.
    '''

    # The UUID field is the unique internal identifier used for this InvoiceItem
    id = models.UUIDField(_('Invoice item number'),primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice,verbose_name=_('Invoice'),on_delete=models.CASCADE)
    description = models.CharField(_('Description'), max_length=300,null=True,blank=True)

    temporaryEventRegistration = models.OneToOneField(
        TemporaryEventRegistration,verbose_name=_('Temporary event registration'),
        null=True,blank=True,on_delete=models.SET_NULL
    )
    finalEventRegistration = models.OneToOneField(EventRegistration,verbose_name=_('Event registration'),null=True,blank=True,on_delete=models.SET_NULL)

    grossTotal = models.FloatField(_('Total before discounts'),validators=[MinValueValidator(0)],default=0)
    total = models.FloatField(_('Total billed amount'),validators=[MinValueValidator(0)], default=0)
    adjustments = models.FloatField(_('Refunds/adjustments'),default=0)
    taxes = models.FloatField(_('Taxes'),validators=[MinValueValidator(0)],default=0)
    fees = models.FloatField(_('Processing fees'), validators=[MinValueValidator(0)],default=0)

    @property
    def netRevenue(self):
        net = self.total - self.fees + self.adjustments
        if not self.invoice.buyerPaysSalesTax:
            net -= self.taxes
        return net
    netRevenue.fget.short_description = _('Net revenue')

    @property
    def name(self):
        er = self.finalEventRegistration or self.temporaryEventRegistration
        if er and er.dropIn:
            return _('Drop-in Registration: %s' % er.event.name)
        elif er:
            return _('Registration: %s' % er.event.name)
        else:
            return self.description or _('Other items')
    name.fget.short_description = _('Name')

    def __str__(self):
        return '%s: #%s' % (self.name, self.id)

    class Meta:
        verbose_name = _('Invoice item')
        verbose_name_plural = _('Invoice items')


class PaymentRecord(PolymorphicModel):
    '''
    All payments to invoices should be recorded using PaymentRecords.  Individual payment
    processors should be subclassed from this base class. Since this is a polymorphic model,
    invoice operations can easily get a list of all payments by querying this model, but can
    still perform operations on individual payment types depending on their features.  The
    only payment method that is enabled by default is the 'Cash' payment method.
    '''

    invoice = models.ForeignKey(Invoice, verbose_name=_('Invoice'), null=True,blank=True,on_delete=models.SET_NULL)

    creationDate = models.DateTimeField(_('Created'),auto_now_add=True)
    modifiedDate = models.DateTimeField(_('Last updated'),auto_now=True)

    submissionUser = models.ForeignKey(User,verbose_name=_('Submission user'), null=True,blank=True,related_name='payments_submitted',on_delete=models.SET_NULL)

    @property
    def refundable(self):
        '''
        Payment methods that can be automatically refunded should override this to return True.
        '''
        return False

    @property
    def methodName(self):
        '''
        Payment methods should override this with a descriptive name.
        '''
        return None

    @property
    def recordId(self):
        '''
        Payment methods should override this if they keep their own unique identifiers.
        '''
        return self.id

    @property
    def netAmountPaid(self):
        '''
        This method should also be overridden by individual payment methods.
        '''
        return None

    def getPayerEmail(self):
        '''
        This method should be overridden by individual payment methods.
        '''
        return None

    def refund(self,amount):
        '''
        This method should be overridden by individual payment methods to process refunds.
        '''
        return False

    class Meta:
        ordering = ('-modifiedDate',)
        verbose_name = _('Payment record')
        verbose_name_plural = _('Payment records')


class CashPaymentRecord(PaymentRecord):

    class PaymentStatus(DjangoChoices):
        needsCollection = ChoiceItem('N',_('Cash payment recorded, needs collection'))
        collected = ChoiceItem('C',_('Cash payment collected'))
        fullRefund = ChoiceItem('R',_('Refunded in full'))

    amount = models.FloatField(_('Amount paid'),validators=[MinValueValidator(0),])
    payerEmail = models.EmailField(_('Payer email'),null=True,blank=True)

    status = models.CharField(_('Payment status'), max_length=1, choices=PaymentStatus.choices,default=PaymentStatus.needsCollection)
    collectedByUser = models.ForeignKey(User,null=True,blank=True,verbose_name=_('Collected by user'),related_name='collectedcashpayments',on_delete=models.SET_NULL)

    @property
    def methodName(self):
        return 'Cash'

    @property
    def netAmountPaid(self):
        return self.amount

    def getPayerEmail(self):
        return self.payerEmail

    class Meta:
        verbose_name = _('Cash payment record')
        verbose_name_plural = _('Cash payment records')


class StaffMemberPluginModel(CMSPlugin):
    ''' Views on an individual staff member or instructor use this model for configuration. '''
    staffMember = models.ForeignKey(StaffMember,verbose_name=_('Staff member'),on_delete=models.CASCADE)
    template = models.CharField(_('Plugin template'),max_length=250,null=True,blank=True)

    def get_short_description(self):
        return self.staffMember.fullName


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
    orderChoice = models.CharField(_('Order By'),max_length=10,choices=OrderChoices.choices)
    imageThumbnail = models.ForeignKey(ThumbnailOption,verbose_name=_('Image thumbnail option'),null=True,blank=True,on_delete=models.SET_NULL)

    bioRequired = models.BooleanField(_('Exclude instructors with no bio'),default=False)
    photoRequired = models.BooleanField(_('Exclude instructors with no photo'),default=False)
    activeUpcomingOnly = models.BooleanField(_('Include only instructors with upcoming classes'),default=False)

    title = models.CharField(_('Listing Title'),max_length=200,null=True,blank=True)
    template = models.CharField(_('Template'),max_length=250,null=True,blank=True)

    def get_short_description(self):
        desc = self.title or ''
        choices = getattr(self.get_plugin_class(),'template_choices',[])
        choice_name = [x[1] for x in choices if x[0] == self.template]
        if choice_name:
            if desc:
                desc += ': %s' % choice_name[0]
            else:
                desc = choice_name[0]
        elif self.template:
            if desc:
                desc += ': %s' % self.template
            else:
                desc = self.template
        return desc or self.id


class LocationListPluginModel(CMSPlugin):
    ''' A model for listing of all active locations '''
    template = models.CharField(verbose_name=_('Plugin template'),max_length=250,null=True,blank=True)

    def get_short_description(self):
        desc = self.id
        choices = getattr(self.get_plugin_class(),'template_choices',[])
        choice_name = [x[1] for x in choices if x[0] == self.template]
        if choice_name:
            desc = choice_name[0]
        elif self.template:
            desc = self.template
        return desc


class LocationPluginModel(CMSPlugin):
    ''' Individual location directions, etc. use this view '''
    location = models.ForeignKey(Location,verbose_name=_('Location'),on_delete=models.CASCADE)
    template = models.CharField(_('Plugin template'),max_length=250,null=True,blank=True)

    def get_short_description(self):
        desc = self.location.name or ''
        choices = getattr(self.get_plugin_class(),'template_choices',[])
        choice_name = [x[1] for x in choices if x[0] == self.template]
        if choice_name:
            if desc:
                desc += ': %s' % choice_name[0]
            else:
                desc = choice_name[0]
        elif self.template:
            if desc:
                desc += ': %s' % self.template
            else:
                desc = self.template
        return desc or self.id


class EventListPluginModel(CMSPlugin):
    '''
    This model is typically used to configure upcoming event listings, but it can be customized to a variety of purposes using
    custom templates, etc.
    '''
    LIMIT_CHOICES = [
        ('S',_('Event start date')),
        ('E',_('Event end date')),
    ]
    EVENT_TYPE_CHOICES = [
        ('S',_('Class Series')),
        ('P',_('Public Events')),
    ]
    SORT_CHOICES = [
        ('A',_('Ascending')),
        ('D',_('Descending')),
    ]

    title = models.CharField(_('Custom list title'),max_length=250,default=_('Upcoming Events'),blank=True)

    eventType = models.CharField(_('Limit to event type'),max_length=1,choices=EVENT_TYPE_CHOICES,null=True,blank=True,help_text=_('Leave blank to include all Events.'))
    limitNumber = models.PositiveSmallIntegerField(_('Limit number'),help_text=_('Leave blank for no restriction'),null=True,blank=True)
    sortOrder = models.CharField(_('Sort by start time'),max_length=1,choices=SORT_CHOICES,default='A',help_text=_('This may be overridden by the particular template in use'))

    limitTypeStart = models.CharField(_('Limit interval start by'),max_length=1,choices=LIMIT_CHOICES,default='E')
    daysStart = models.SmallIntegerField(_('Interval limited to __ days from present'),null=True,blank=True,help_text=_('(E.g. enter -30 for an interval that starts with 30 days prior to today) Leave blank for no limit, or enter 0 to limit to future events'))
    startDate = models.DateField(_('Exact interval start date'),null=True,blank=True,help_text=_('Leave blank for no limit (overrides relative interval limits)'))

    limitTypeEnd = models.CharField(_('Limit interval end by'),max_length=1,choices=LIMIT_CHOICES,default='S')
    daysEnd = models.SmallIntegerField(_('Interval limited to __ days from present'),null=True,blank=True,help_text=_('(E.g. enter 30 for an interval that ends 30 days from today) Leave blank for no limit, or enter 0 to limit to past events'))
    endDate = models.DateField(_('Exact interval end date '),null=True,blank=True,help_text=_('Leave blank for no limit (overrides relative interval limits)'))

    limitToOpenRegistration = models.BooleanField(_('Limit to open for registration only'),default=False)
    location = models.ManyToManyField(Location,verbose_name=_('Limit to locations'),help_text=_('Leave blank for no restriction'),blank=True)
    weekday = models.PositiveSmallIntegerField(_('Limit to weekday'),null=True,blank=True,choices=[(x,_(day_name[x])) for x in range(0,7)])

    eventCategories = models.ManyToManyField(
        PublicEventCategory,verbose_name=_('Limit to public event categories'),
        help_text=_('Leave blank for no restriction'),
        blank=True
    )

    seriesCategories = models.ManyToManyField(
        SeriesCategory,verbose_name=_('Limit to series categories'),
        help_text=_('Leave blank for no restriction'),
        blank=True
    )

    levels = models.ManyToManyField(
        DanceTypeLevel,verbose_name=_('Limit to type and levels'),
        help_text=_('Leave blank for no restriction'),
        blank=True
    )

    cssClasses = models.CharField(_('Custom CSS classes'),max_length=250,null=True,blank=True,help_text=_('Classes are applied to surrounding &lt;div&gt;'))
    template = models.CharField(_('Plugin template'),max_length=250,null=True,blank=True)

    def copy_relations(self, oldinstance):
        self.location = oldinstance.location.all()
        self.eventCategories = oldinstance.eventCategories.all()
        self.seriesCategories = oldinstance.seriesCategories.all()
        self.levels = oldinstance.levels.all()

    def get_short_description(self):
        desc = self.title or ''
        choices = getattr(self.get_plugin_class(),'template_choices',[])
        choice_name = [x[1] for x in choices if x[0] == self.template]
        if choice_name:
            if desc:
                desc += ': %s' % choice_name[0]
            else:
                desc = choice_name[0]
        elif self.template:
            if desc:
                desc += ': %s' % self.template
            else:
                desc = self.template
        return desc or self.id

    class Meta:
        permissions = (
            ('choose_custom_plugin_template',_('Can enter a custom plugin template for plugins with selectable template.')),
        )
