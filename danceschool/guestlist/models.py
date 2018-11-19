from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Value, Case, When, F
from django.db.models.functions import Concat
from django.utils.translation import ugettext_lazy as _, ugettext
from django.utils import timezone

from cms.models.pluginmodel import CMSPlugin
from intervaltree import IntervalTree
from datetime import timedelta
from dateutil.relativedelta import relativedelta

from danceschool.core.models import PublicEventCategory, SeriesCategory, EventStaffCategory, EventSession, Event, StaffMember, Registration
from danceschool.core.utils.timezone import ensure_localtime
from .constants import GUESTLIST_ADMISSION_CHOICES, GUESTLIST_SORT_CHOICES


class GuestList(models.Model):

    name = models.CharField(_('Name'),max_length=200,unique=True)
    sortOrder = models.CharField(_('Sort order'),choices=GUESTLIST_SORT_CHOICES,default='Last',max_length=5)

    # Rules for which events a guest list applies to
    seriesCategories = models.ManyToManyField(SeriesCategory,verbose_name=_('Series categories'),blank=True)
    eventCategories = models.ManyToManyField(PublicEventCategory,verbose_name=_('Public event categories'),blank=True)
    eventSessions = models.ManyToManyField(EventSession,verbose_name=_('Event sessions'),blank=True)
    individualEvents = models.ManyToManyField(Event,verbose_name=_('Individual events'),blank=True,related_name='specifiedGuestLists')

    includeStaff = models.BooleanField(_('Include all scheduled event staff'),default=True,blank=True)
    includeRegistrants = models.BooleanField(_('Include event registrants'),default=True,blank=True)

    @property
    def recentEvents(self):
        '''
        Get the set of recent and upcoming events to which this list applies.
        '''
        return Event.objects.filter(
            Q(pk__in=self.individualEvents.values_list('pk',flat=True)) |
            Q(session__in=self.eventSessions.all()) |
            Q(publicevent__category__in=self.eventCategories.all()) |
            Q(series__category__in=self.seriesCategories.all())
        ).filter(
            Q(startTime__lte=timezone.now() + timedelta(days=60)) &
            Q(endTime__gte=timezone.now() - timedelta(days=60))
        )

    @property
    def currentEvent(self):
        '''
        Return the first event that hasn't ended yet, or if there are no
        future events, the last one to end.
        '''
        currentEvent =  self.recentEvents.filter(endTime__gte=timezone.now()).order_by('startTime').first()
        if not currentEvent:
            currentEvent = self.recentEvents.filter(
                endTime__lte=timezone.now()
            ).order_by('-endTime').first()
        return currentEvent

    def appliesToEvent(self, event):
        ''' Check whether this guest list is applicable to an event. '''
        return (
            event in self.individualEvents.all() or
            event.session in self.eventSessions.all() or
            event.category in self.seriesCategories.all() or
            event.category in self.eventCategories.all()
        ) 

    def getDayStart(self, dateTime):
        ''' Ensure local time and get the beginning of the day '''
        return ensure_localtime(dateTime).replace(hour=0,minute=0,second=0,microsecond=0)

    def getComponentFilters(self,component,event=None,dateTime=None):
        '''
        Get a parsimonious set of intervals and the associated Q() objects
        based on the occurrences of a specified event, and the rule that
        implicitly defines the start and end of each interval.
        '''

        # Limit to the staff member or staff category specified by the rule.
        if component.staffMember:
            filters = Q(pk=component.staffMember.pk)
        else:
            filters = Q(eventstaffmember__category=component.staffCategory)

        # Handle 'Always' and 'EventOnly' rules first, because they do not require an analysis of intervals.
        if component.admissionRule == 'EventOnly' and event:
            # Skip the analysis of intervals and include only those who are staffed for the event.
            return Q(filters & Q(eventstaffmember__event=event))
        elif component.admissionRule in ['Always','EventOnly']:
            # If 'Always' or no event is specified, include all associated staff
            return Q(filters)

        # Start with the event occurrence intervals, or with the specified time.
        if event:
            intervals = [(x.startTime,x.endTime) for x in event.eventoccurrence_set.all()]
        elif dateTime:
            intervals = [(dateTime,dateTime)]
        else:
            raise ValueError(_('Must provide either an event or a datetime to get interval queries.'))

        if component.admissionRule == 'Day':
            # The complete days of each event occurrence
            intervals = [
                (self.getDayStart(x[0]),self.getDayStart(x[1]) + timedelta(days=1)) for x in intervals
            ]
        elif component.admissionRule == 'Week':
            # The complete weeks of each event occurrence
            intervals = [
                (
                    self.getDayStart(x[0]) - timedelta(days=x[0].weekday()),
                    self.getDayStart(x[1]) - timedelta(days=x[1].weekday() - 7)
                ) for x in intervals
            ]
        elif component.admissionRule == 'Month':
            # The complete month of each event occurrence
            intervals = [
                (
                    self.getDayStart(x[0]).replace(day=1),
                    self.getDayStart(x[1]).replace(day=1) + relativedelta(months=1)
                ) for x in intervals
            ]
        elif component.admissionRule == 'Year':
            # The complete years of each event occurrence
            intervals = [
                (
                    self.getDayStart(x[0]).replace(month=1,day=1),
                    self.getDayStart(x[1]).replace(year=x[1].year + 1,month=1,day=1)
                ) for x in intervals
            ]
        else:
            # This is a failsafe that will always evaluate as False.
            return Q(pk__isnull=True)

        # Use intervaltree to create the most parsimonious set of intervals for this interval
        # and then filter on those intervals
        intervals = [sorted(x) for x in intervals]
        tree = IntervalTree.from_tuples(intervals)
        tree.merge_overlaps()

        # Since we are OR appending, start with something that is always False.
        intervalFilters = Q(pk__isnull=True)

        for item in tree.items():
            intervalFilters = intervalFilters | Q(
                Q(eventstaffmember__event__eventoccurrence__endTime__gte=item[0]) &
                Q(eventstaffmember__event__eventoccurrence__startTime__lte=item[1])
            )

        return Q(filters & intervalFilters)

    def getListForEvent(self, event=None):
        ''' Get the list of names associated with a particular event. '''
        names = list(self.guestlistname_set.annotate(
            guestType=Case(
                When(notes__isnull=False, then=F('notes')),
                default=Value(ugettext('Manually Added')),
                output_field=models.CharField()
            )
        ).values('firstName','lastName','guestType'))

        # Component-by-component, OR append filters to an initial filter that always
        # evaluates to False.
        components = self.guestlistcomponent_set.all()
        filters = Q(pk__isnull=True)

        # Add prior staff based on the component rule.
        for component in components:
            if event and self.appliesToEvent(event):
                filters = filters | self.getComponentFilters(component,event=event)
            else:
                filters = filters | self.getComponentFilters(component,dateTime=timezone.now())

        # Add all event staff if that box is checked (no need for separate components)
        if self.includeStaff and event and self.appliesToEvent(event):
            filters = filters | Q(eventstaffmember__event=event)

        # Execute the constructed query and add the names of staff
        names += list(StaffMember.objects.filter(filters).annotate(
            guestType=Case(
                When(eventstaffmember__event=event, then=Concat(Value('Event Staff: '), 'eventstaffmember__category__name')),
                default=Value(ugettext('Other Staff')),
                output_field=models.CharField()
            )
        ).distinct().values('firstName','lastName','guestType'))

        if self.includeRegistrants and event and self.appliesToEvent(event):
            names += list(Registration.objects.filter(eventregistration__event=event).annotate(
                guestType=Value(_('Registered'),output_field=models.CharField())
            ).values('firstName','lastName','guestType'))
        return names


    def __str__(self):
        return '%s: %s' % (_('Guest list'),self.name)

    class Meta:
        ordering = ('name',)
        verbose_name = _('Guest list')
        verbose_name_plural = _('Guest lists')


class GuestListName(models.Model):
    ''' Additional names to be manually added to a particular guest list '''

    guestList = models.ForeignKey(GuestList,on_delete=models.CASCADE)
    firstName = models.CharField(_('First name'),max_length=50)
    lastName = models.CharField(_('Last name'),max_length=50)

    notes = models.CharField(_('Notes (optional)'),help_text=_('These will be included on the list for reference.'),null=True,blank=True,max_length=200)

    @property
    def fullName(self):
        return ' '.join([self.firstName or '',self.lastName or ''])
    fullName.fget.short_description = _('Name')

    def __str__(self):
        return '%s: %s' % (_('Guest'), self.fullName)

    class Meta:
        ordering = ('guestList', 'lastName','firstName')
        verbose_name = _('Manually-added guest')
        verbose_name_plural = _('Manually added guests')
        permissions = (
            ('view_guestlist',_('Can view guest lists')),
        )


class GuestListComponent(models.Model):
    guestList = models.ForeignKey(GuestList,on_delete=models.CASCADE)

    staffCategory = models.ForeignKey(EventStaffCategory,verbose_name=_('Category of staff members'),null=True, blank=True, on_delete=models.CASCADE)
    staffMember = models.ForeignKey(StaffMember,verbose_name=_('Individual staff member'),null=True,blank=True,on_delete=models.CASCADE)

    admissionRule = models.CharField(_('Event admission rule'),choices=GUESTLIST_ADMISSION_CHOICES,max_length=10)

    def clean(self):
        ''' Either staffCategory or staffMember must be filled in, but not both. '''
        if not self.staffCategory and not self.staffMember:
            raise ValidationError(_('Either staff category or staff member must be specified.'))
        if self.staffCategory and self.staffMember:
           raise ValidationError(_('Specify either a staff category or a staff member, not both.'))      

    class Meta:
        ordering = ('guestList','admissionRule')
        verbose_name = _('Guest list component')
        verbose_name_plural = _('Guest list components')
        unique_together = ('guestList','staffCategory','staffMember')
