from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from datetime import timedelta
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

    def __str__(self):
        return _('Instructor Private lesson details for %s' % self.instructor.fullName)

    class Meta:
        ordering = ('instructor__lastName','instructor__firstName')
        verbose_name = _('Instructor private lesson details')
        verbose_name_plural = _('Instructors\' private lesson details')


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

    def finalizeBooking(self,**kwargs):
        notifyStudent = kwargs.get('notifyStudent',True)
        notifyTeachers = kwargs.get('notifyTeachers',getConstant('privateLessons__notifyInstructor'))
        eventRegistration = kwargs.get('eventRegistration',None)

        affectedSlots = self.instructoravailabilityslot_set.all()
        affectedSlots.update(
            status=InstructorAvailabilitySlot.SlotStatus.booked,
            eventRegistration=eventRegistration,
        )

        if notifyStudent:
            pass

        if notifyTeachers:
            pass

    @property
    def name(self):
        ''' TODO: Add instructor and time information to this '''
        return _('Private Lesson Event: %s' % self.startTime)

    def __str__(self):
        return str(self.name)

    class Meta:
        verbose_name = _('Private lesson')
        verbose_name_plural = _('Private lessons')


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
            self.startTime >= dateTime and not self.eventRegistration and (
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
        return _('%s: %s at %s') % (self.instructor.fullName, ensure_localtime(self.startTime).strftime('%b %-d, %Y %-I:%M %p'), self.location)

    def __str__(self):
        return str(self.name)

    class Meta:
        ordering = ('-startTime','instructor__lastName','instructor__firstName')
        verbose_name = _('Private lesson availability slot')
        verbose_name_plural = _('Private lesson availability slots')

        permissions = (
            ('edit_own_availability',_('Can edit one\'s own private lesson availability.')),
            ('edit_others_availability',_('Can edit other instructors\' private lesson availability.')),
        )
