from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from calendar import day_name
from multiselectfield import MultiSelectField
from datetime import datetime, timedelta
from djchoices import DjangoChoices, ChoiceItem

from danceschool.core.models import Instructor, Location, DanceRole, Event, PricingTier, TemporaryEventRegistration, EventRegistration
from danceschool.core.constants import getConstant
from danceschool.core.utils.timezone import ensure_localtime


class InstructorPrivateLessonDetails(models.Model):
    instructor = models.OneToOneField(Instructor)
    defaultPricingTier = models.ForeignKey(
        PricingTier,verbose_name=_('Default Pricing Tier'),null=True,blank=True
    )
    roles = models.ManyToManyField(DanceRole,blank=True)

    couples = models.BooleanField(_('Private lessons for couples'),default=True)
    smallGroups = models.BooleanField(_('Private lessons for small groups'), default=True)


class PrivateLessonEvent(Event):
    '''
    This is the event object for which an individual registers.  The event is created when the user books a lesson.
    All of the registration logic is still handled by the core app, and this model inherits all of the fields
    associated with other types of events (location, etc.)
    '''

    pricingTier = models.ForeignKey(PricingTier,verbose_name=_('Pricing Tier'))
    participants = models.PositiveSmallIntegerField(_('Expected # of Participants'),null=True,blank=True,default=1)
    comments = models.TextField(
        _('Comments/Notes'),null=True,blank=True,help_text=_('For internal use and recordkeeping.')
    )

    def getBasePrice(self,**kwargs):
        '''
        This method overrides the method of the base Event class by
        checking the pricingTier associated with this PrivateLessonEvent and getting
        the appropriate price for it.
        '''
        if not self.pricingTier:
            return None
        return self.pricingTier.getBasePrice(**kwargs)

    @property
    def name(self):
        ''' TODO: Add instructor and time information to this '''
        return _('Private Lesson Event: %s' % self.startTime)

    def __str__(self):
        return str(self.name)


class InstructorAvailabilityRule(models.Model):
    '''
    Availability rules are used to simplify the creation
    of availability slots.
    '''
    instructor = models.ForeignKey(Instructor)

    startDate = models.DateField(_('Start date'))
    endDate = models.DateField(_('End date'))
    weekdays = MultiSelectField(
        verbose_name=_('Limit to days of the week'),
        choices=[(x,day_name[x]) for x in range(0,7)]
    )

    startTime = models.TimeField(_('Start time'))
    endTime = models.TimeField(_('End time'))
    location = models.ForeignKey(Location,verbose_name=_('Location'),null=True,blank=True)

    creationDate = models.DateTimeField(auto_now_add=True)

    def createSlots(self,startDate=None,endDate=None,interval_minutes=None):
        if not startDate:
            startDate = max(
                (timezone.now() + timedelta(days=getConstant('privatelessons__CloseBookingDays'))).date(),
                self.startDate
            )
        if not endDate:
            endDate = min(
                (timezone.now() + timedelta(days=getConstant('privatelessons__OpenBookingDays'))).date(),
                self.endDate
            )
        if not interval_minutes:
            interval_minutes = getConstant('privateLessons__lessonLengthInterval')

        this_date = startDate
        while this_date <= endDate:
            if (
                this_date.weekday() in self.weekdays and
                this_date >= self.startDate and
                this_date <= self.endDate
            ):
                this_time = self.startTime
                while this_time < self.endTime:
                    InstructorAvailabilitySlot.objects.create(
                        instructor=self.instructor,
                        startTime=ensure_localtime(datetime.combine(this_date, this_time)),
                        duration=interval_minutes,
                        location=self.location
                    )
                    this_time = (ensure_localtime(datetime.combine(this_date, this_time)) + timedelta(minutes=interval_minutes)).time()

            this_date += timedelta(days=1)


class InstructorAvailabilitySlot(models.Model):

    class SlotStatus(DjangoChoices):
        available = ChoiceItem('A',_('Available'))
        booked = ChoiceItem('B',_('Booked'))
        tentative = ChoiceItem('T',_('Tentative Booking'))
        unavailable = ChoiceItem('U',_('Unavailable'))

    instructor = models.ForeignKey(Instructor,verbose_name=_('Instructor'),on_delete=models.CASCADE)
    pricingTier = models.ForeignKey(
        PricingTier,verbose_name=_('Pricing Tier'),null=True,blank=True,on_delete=models.SET_NULL
    )
    startTime = models.DateTimeField(_('Start time'))
    duration = models.PositiveSmallIntegerField(_('Slot duration (minutes)'),default=30)
    location = models.ForeignKey(
        Location,verbose_name=_('Location'),null=True,blank=True,on_delete=models.SET_NULL,
    )

    status = models.CharField(max_length=1,choices=SlotStatus.choices,default=SlotStatus.available)

    # We need both a link to the registrations and a link to the event because
    # in the event that an expired TemporaryRegistration is deleted, we still want to
    # be able to identify the Event that was created for this private lesson.
    lessonEvent = models.ForeignKey(
        PrivateLessonEvent,verbose_name=_('Scheduled lesson'),null=True,blank=True,
        on_delete=models.SET_NULL,
    )
    temporaryEventRegistration = models.ForeignKey(
        TemporaryEventRegistration,verbose_name=_('Temporary event registration'),
        null=True,blank=True,on_delete=models.SET_NULL,related_name='privateLessonSlots'
    )
    eventRegistration = models.ForeignKey(
        EventRegistration,verbose_name=_('Final event registration'),
        null=True,blank=True,on_delete=models.SET_NULL,related_name='privateLessonSlots'
    )

    creationDate = models.DateTimeField(auto_now_add=True)
    modifiedDate = models.DateTimeField(auto_now=True)

    @property
    def availableDurations(self):
        '''
        A lesson can always be booked for the length of a single slot, but this method
        checks if multiple slots are available.  This method requires that slots are
        non-overlapping, which needs to be enforced on slot save.
        '''
        potential_slots = InstructorAvailabilitySlot.objects.filter(
            instructor=self.instructor,
            location=self.location,
            pricingTier=self.pricingTier,
            startTime__gte=self.startTime,
            startTime__lte=self.startTime + timedelta(minutes=getConstant('privateLessons__maximumLessonLength')),
        ).exclude(id=self.id).order_by('startTime')

        duration_list = [self.duration,]
        last_start = self.startTime
        last_duration = self.duration
        max_duration = self.duration

        for slot in potential_slots:
            if max_duration + slot.duration > getConstant('privateLessons__maximumLessonLength'):
                break
            if (
                slot.startTime == last_start + timedelta(minutes=last_duration) and
                slot.isAvailable
            ):
                duration_list.append(max_duration + slot.duration)
                last_start = slot.startTime
                last_duration = slot.duration
                max_duration += slot.duration

        return duration_list

    @property
    def availableRoles(self):
        '''
        Some instructors only offer private lessons for certain roles, so we should only allow booking
        for the roles that have been selected for the instructor.
        '''
        if not hasattr(self.instructor,'instructorprivatelessondetails'):
            return []
        return [
            [x.id,x.name] for x in
            self.instructor.instructorprivatelessondetails.roles.all()
        ]

    def checkIfAvailable(self, dateTime=timezone.now()):
        '''
        Available slots are available, but also tentative slots that have been held as tentative
        past their expiration date
        '''
        return (
            self.startTime >= dateTime and not self.registration and (
                self.status == self.SlotStatus.available or (
                    self.status == self.SlotStatus.tentative and
                    getattr(getattr(self.temporaryEventRegistration,'registration',None),'expirationDate',timezone.now()) <= timezone.now()
                )
            )
        )
    # isAvailable indicates if a slot is currently available
    isAvailable = property(fget=checkIfAvailable)
    isAvailable.fget.short_description = _('Available')

    @property
    def name(self):
        return '%s: %s at %s' % (self.instructor.fullName, self.startTime, self.location)
