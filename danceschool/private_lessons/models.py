from django.db import models
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone
from django.core.urlresolvers import reverse

from datetime import timedelta
from djchoices import DjangoChoices, ChoiceItem

from danceschool.core.models import Instructor, Location, Room, DanceRole, Event, PricingTier, TemporaryEventRegistration, EventRegistration, Customer
from danceschool.core.constants import getConstant
from danceschool.core.mixins import EmailRecipientMixin
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
        return str(_('Instructor Private lesson details for %s' % self.instructor.fullName))

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

    pricingTier = models.ForeignKey(PricingTier,verbose_name=_('Pricing Tier'),null=True,blank=True)
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
        return self.pricingTier.getBasePrice(**kwargs) * max(self.numSlots,1)

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
            # This is the email template used to notify students that their private lesson has been
            # successfully scheduled

            template = getConstant('privateLessons__lessonBookedEmailTemplate')

            if template.defaultFromAddress and template.content:
                for customer in self.customers:
                    customer.email_recipient(
                        template.subject,
                        template.content,
                        send_html=False,
                        from_address=template.defaultFromAddress,
                        from_name=template.defaultFromName,
                        cc=template.defaultCC,
                        to=customer.email,
                        lesson=self,
                    )

        if notifyTeachers:
            # This is the email template used to notify individuals who run registration
            # that they have been compensated
            template = getConstant('privateLessons__lessonBookedInstructorEmailTemplate')

            if template.defaultFromAddress and template.content:
                emailMixin = EmailRecipientMixin()

                instructors = [
                    x.staffMember for x in
                    self.eventstaffmember_set.exclude(
                        Q(staffMember__privateEmail__isnull=True) & Q(staffMember__publicEmail__isnull=True)
                    )
                ]

                for instructor in instructors:
                    if not instructor.privateEmail and not instructor.publicEmail:
                        # Without an email address, instructor cannot be notified
                        continue
                    emailMixin.email_recipient(
                        template.subject,
                        template.content,
                        send_html=False,
                        from_address=template.defaultFromAddress,
                        from_name=template.defaultFromName,
                        cc=template.defaultCC,
                        to=instructor.privateEmail or instructor.publicEmail,
                        lesson=self,
                        instructor=instructor,
                        customers=self.customers,
                        calendarUrl=reverse('privateCalendar'),
                    )

    @property
    def customers(self):
        '''
        List both any individuals signed up via the registration and payment system,
        and any individuals signed up without payment.
        '''
        return Customer.objects.filter(
            Q(privatelessoncustomer__lesson=self) |
            Q(registration__eventregistration__event=self)
        ).distinct()
    customers.fget.short_description = _('Customers')

    @property
    def numSlots(self):
        ''' Used for various pricing discounts related things '''
        return self.instructoravailabilityslot_set.count()

    @property
    def discountPointsMultiplier(self):
        '''
        If installed, the discounts app looks for this property to determine
        how many points this lesson is worth toward a discount.  Since private
        lesson points are based on the number of slots booked, this just returns
        the number of slots associated with this event (or 1).
        '''
        return max(self.numSlots,1)

    def nameAndDate(self,withDate=True):
        teacherNames = ' and '.join([x.staffMember.fullName for x in self.eventstaffmember_set.all()])
        if self.customers:
            customerNames = ' ' + ' and '.join([x.fullName for x in self.customers])
        elif self.temporaryeventregistration_set.all():
            names = ' and '.join([x.registration.fullName for x in self.temporaryeventregistration_set.all()])
            customerNames = ' ' + names if names else ''
        else:
            customerNames = ''

        if not teacherNames and not customerNames and not withDate:
            return _('Private Lesson')

        return _('Private Lesson: %s%s%s%s' % (
            teacherNames,
            _(' for ') if teacherNames and customerNames else '',
            customerNames,
            ((', ' if (teacherNames or customerNames) else '') + self.startTime.strftime('%Y-%m-%d')) if withDate else ''
        ))

    @property
    def name(self):
        return self.nameAndDate(withDate=True)

    def save(self, *args, **kwargs):
        ''' Set registration status to hidden if it is not specified otherwise '''
        if not self.status:
            self.status == Event.RegStatus.hidden
        super(PrivateLessonEvent,self).save(*args,**kwargs)

    def __str__(self):
        return str(self.name)

    class Meta:
        permissions = (
            ('view_others_lessons',_('Can view scheduled private lessons for all instructors')),
        )

        verbose_name = _('Private lesson')
        verbose_name_plural = _('Private lessons')


class PrivateLessonCustomer(models.Model):
    '''
    For private lessons that go through registration and payment, the customers
    are the individuals who are registered.  For private lessons that are booked
    without payment, this just provides a record that they signed up for
    the lesson.
    '''
    customer = models.ForeignKey(Customer,verbose_name=_('Customer'))
    lesson = models.ForeignKey(PrivateLessonEvent,verbose_name=_('Lesson'))

    def __str__(self):
        return str(_('Private lesson customer: %s for lesson #%s' % (self.customer.fullName, self.lesson.id)))

    class Meta:
        unique_together = ('customer','lesson')
        verbose_name = _('Private lesson customer')
        verbose_name_plural = _('Private lesson customers')


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
    room = models.ForeignKey(
        Room,verbose_name=_('Room'),null=True,blank=True,on_delete=models.SET_NULL,
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
            room=self.room,
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
            self.startTime >= dateTime + timedelta(days=getConstant('privateLessons__closeBookingDays')) and
            self.startTime <= dateTime + timedelta(days=getConstant('privateLessons__openBookingDays')) and not
            self.eventRegistration and (
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
