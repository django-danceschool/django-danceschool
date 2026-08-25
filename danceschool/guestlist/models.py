from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Value, Case, When, F, Exists, OuterRef, Subquery
from django.db.models.functions import Concat, Coalesce
from django.utils.translation import gettext_lazy as _, gettext
from django.utils import timezone

from intervaltree import IntervalTree
from datetime import timedelta
from dateutil.relativedelta import relativedelta

from danceschool.core.models import (
    PublicEventCategory, SeriesCategory, EventStaffCategory, EventSession,
    Event, StaffMember, EventRegistration, EventOccurrence
)
from danceschool.core.utils.timezone import ensure_localtime
from .constants import (
    GUESTLIST_ADMISSION_CHOICES, GUESTLIST_REGISTRATION_ADMISSION_CHOICES,
    GUESTLIST_SORT_CHOICES
)


class GuestList(models.Model):

    name = models.CharField(_('Name'), max_length=200, unique=True)
    sortOrder = models.CharField(_('Sort order'), choices=GUESTLIST_SORT_CHOICES, default='Last', max_length=5)

    # Rules for which events a guest list applies to
    seriesCategories = models.ManyToManyField(
        SeriesCategory, verbose_name=_('Series categories'), blank=True
    )
    eventCategories = models.ManyToManyField(
        PublicEventCategory, verbose_name=_('Public event categories'), blank=True
    )
    eventSessions = models.ManyToManyField(
        EventSession, verbose_name=_('Event sessions'), blank=True
    )
    individualEvents = models.ManyToManyField(
        Event, verbose_name=_('Individual events'), blank=True,
        related_name='specifiedGuestLists'
    )

    includeStaff = models.BooleanField(_('Include all scheduled event staff'), default=True, blank=True)
    includeRegistrants = models.BooleanField(_('Include event registrants'), default=True, blank=True)

    @property
    def recentEvents(self):
        '''
        Get the set of recent and upcoming events to which this list applies.
        '''
        return Event.objects.filter(
            Q(pk__in=self.individualEvents.values_list('pk', flat=True)) |
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
        currentEvent = self.recentEvents.filter(endTime__gte=timezone.now()).order_by('startTime').first()
        if not currentEvent:
            currentEvent = self.recentEvents.filter(
                endTime__lte=timezone.now()
            ).order_by('-endTime').first()
        return currentEvent

    def appliesToEvents(self, events, verbose=False):
        ''' Check whether this guest list is applicable to an event. '''
        applies = True
        verbose_response = {}

        # These use prefetch cache if prefetch_related was used on the GuestList
        # queryset
        applicable_event_ids = {e.pk for e in self.individualEvents.all()}
        applicable_session_ids = {s.pk for s in self.eventSessions.all()}
        applicable_series_cat_ids = {c.pk for c in self.seriesCategories.all()}
        applicable_event_cat_ids = {c.pk for c in self.eventCategories.all()}

        for event in events:
            if not (
                event.pk in applicable_event_ids or
                event.session_id in applicable_session_ids or    # use _id suffix, no extra query
                event.category_id in applicable_series_cat_ids or  # same
                event.category_id in applicable_event_cat_ids
            ):
                applies = False
                verbose_response[event.id] = False
            else:
                verbose_response[event.id] = True

        if verbose:
            return verbose_response
        return applies

    def getDayStart(self, dateTime):
        ''' Ensure local time and get the beginning of the day '''
        return ensure_localtime(dateTime).replace(hour=0, minute=0, second=0, microsecond=0)

    def getIntervals(
            self, component, events=None, dateTime=None, event_intervals=None
    ):
        '''
        Get a parsimonious set of time intervals based on the occurrences of a
        specified event, and the rule that implicitly defines the start and end
        of each interval.  Returns None for rules that do not depend on
        intervals at all ('Always' and 'EventOnly'), and an empty list for
        unrecognized rules or when there are no occurrences to work from.  This
        logic is shared by all types of guest list component.
        '''

        if component.admissionRule in ['Always', 'EventOnly']:
            return None

        # Start with the event occurrence intervals, or with the specified time.
        if events:
            intervals = event_intervals if event_intervals is not None else [
                (x.startTime, x.endTime) for x in
                EventOccurrence.objects.filter(event__in=events)
            ]
        elif dateTime:
            intervals = [(dateTime, dateTime)]
        else:
            raise ValueError(_(
                'Must provide either an event or a datetime to get interval queries.'
            ))

        if component.admissionRule == 'Day':
            # The complete days of each event occurrence
            intervals = [
                (self.getDayStart(x[0]), self.getDayStart(x[1]) + timedelta(days=1))
                for x in intervals
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
                    self.getDayStart(x[0]).replace(month=1, day=1),
                    self.getDayStart(x[1]).replace(year=x[1].year + 1, month=1, day=1)
                ) for x in intervals
            ]
        elif component.admissionRule == 'Rolling':
            # A rolling window of whole days before and after each event
            # occurrence.  Unlike the calendar-based rules above, this does not
            # depend on where the event falls within the week or month.
            intervals = [
                (
                    self.getDayStart(x[0]) - timedelta(days=component.daysBefore or 0),
                    self.getDayStart(x[1]) + timedelta(days=(component.daysAfter or 0) + 1)
                ) for x in intervals
            ]
        else:
            # This is a failsafe that will always evaluate as False.
            return []

        if not intervals:
            return []

        # Use intervaltree to create the most parsimonious set of intervals for this interval
        # and then filter on those intervals
        intervals = [sorted(x) for x in intervals]
        tree = IntervalTree.from_tuples(intervals)
        tree.merge_overlaps()

        return [(x[0], x[1]) for x in tree.items()]

    def getStaffComponentFilters(
            self, component, events=None, dateTime=None, event_intervals=None
    ):
        '''
        Get the Q() object that identifies the staff members added to this list
        by a specified GuestListStaffComponent.
        '''

        # Limit to the staff member or staff category specified by the rule.
        if component.staffMember:
            filters = Q(pk=component.staffMember.pk)
        else:
            filters = Q(eventstaffmember__category=component.staffCategory)

        # Handle 'Always' and 'EventOnly' rules first, because they do not
        # require an analysis of intervals.
        if component.admissionRule == 'Always' and component.staffMember:
            # A specific named person is always on the list regardless of scheduling.
            return Q(filters)
        elif component.admissionRule in ['Always', 'EventOnly'] and events:
            # For category-based 'Always' and all 'EventOnly' rules, restrict to
            # staff scheduled for these events. This avoids surfacing historical
            # category members who are no longer active.
            return Q(filters & Q(eventstaffmember__event__in=events))
        elif component.admissionRule in ['Always', 'EventOnly']:
            # No events provided; include all associated staff.
            return Q(filters)

        intervals = self.getIntervals(
            component, events=events, dateTime=dateTime,
            event_intervals=event_intervals
        )

        # Since we are OR appending, start with something that is always False.
        intervalFilters = Q(pk__isnull=True)

        for item in intervals or []:
            intervalFilters = intervalFilters | Q(
                Q(eventstaffmember__event__eventoccurrence__endTime__gte=item[0]) &
                Q(eventstaffmember__event__eventoccurrence__startTime__lte=item[1])
            )

        return Q(filters & intervalFilters)

    def getRegistrationComponentFilters(
            self, component, events=None, dateTime=None, event_intervals=None
    ):
        '''
        Get the Q() object that identifies the EventRegistrations which qualify
        an individual for this list under a specified
        GuestListRegistrationComponent.  The categories specified by the
        component determine which registrations qualify, and the admission rule
        determines how close in time the qualifying event must be.
        '''

        seriesCategories = [x.pk for x in component.seriesCategories.all()]
        eventCategories = [x.pk for x in component.eventCategories.all()]

        if not (seriesCategories or eventCategories):
            # A component with no scope specified never adds anyone.
            return Q(pk__isnull=True)

        categoryFilters = Q(pk__isnull=True)

        if seriesCategories:
            categoryFilters = categoryFilters | Q(
                event__series__category__in=seriesCategories
            )
        if eventCategories:
            categoryFilters = categoryFilters | Q(
                event__publicevent__category__in=eventCategories
            )

        intervals = self.getIntervals(
            component, events=events, dateTime=dateTime,
            event_intervals=event_intervals
        )

        intervalFilters = Q(pk__isnull=True)

        for item in intervals or []:
            intervalFilters = intervalFilters | Q(
                Q(event__eventoccurrence__endTime__gte=item[0]) &
                Q(event__eventoccurrence__startTime__lte=item[1])
            )

        return Q(categoryFilters & intervalFilters)

    def getStaffForEvents(
            self, events=Event.objects.none(), filters=Q(),
            startTime=None, endTime=None
        ):
        components = self.guestliststaffcomponent_set.all()  # uses prefetch cache
        component_filters = Q(pk__isnull=True)

        # Compute once, reuse everywhere
        applies_to_all = bool(events) and self.appliesToEvents(events)
        per_event_applies = {}
        event_intervals = None
        if bool(events):
            occ_query = EventOccurrence.objects.filter(event__in=events)
            if startTime is not None and endTime is not None:
                occ_query = occ_query.filter(endTime__gte=startTime, startTime__lte=endTime)

            event_intervals = [
                (x.startTime, x.endTime)
                for x in occ_query
            ]
            if not applies_to_all:
                per_event_applies = self.appliesToEvents(events, verbose=True)
        for component in components:
            if applies_to_all:
                component_filters |= self.getStaffComponentFilters(
                    component, events=events, event_intervals=event_intervals
                )
            elif bool(events):
                for event in events:
                    if per_event_applies.get(event.id):
                        component_filters |= self.getStaffComponentFilters(
                            component, events=[event],
                            event_intervals=event_intervals
                        )
            else:
                component_filters |= self.getStaffComponentFilters(
                    component, dateTime=timezone.now()
                )

        if self.includeStaff and bool(events):
            if applies_to_all:
                component_filters |= Q(eventstaffmember__event__in=events)
            else:
                for event in events:
                    if per_event_applies.get(event.id):
                        component_filters |= Q(eventstaffmember__event=event)

        return StaffMember.objects.filter(component_filters).annotate(
            first=F('firstName'), last=F('lastName'),
            contact=F('privateEmail'), email=F('privateEmail'),
        ).filter(filters)

    def getRegistrantsForEvents(
            self, events=Event.objects.none(), filters=Q(),
            startTime=None, endTime=None
        ):
        '''
        Get the set of EventRegistrations that qualify an individual for
        admission to the specified events under one of this list's
        registration-based components.  This is how, for example, registration
        in a class series can also admit an individual to a social dance later
        in the same week without generating a second EventRegistration.

        Individuals who hold a registration for one of the specified events are
        excluded, because they are already handled as registrants and should
        not be checked in twice.  At most one qualifying registration per
        customer is returned for the same reason.
        '''

        components = self.guestlistregistrationcomponent_set.all()  # uses prefetch cache

        if not components or not events:
            return EventRegistration.objects.none()

        applies_to_all = self.appliesToEvents(events)
        per_event_applies = (
            {} if applies_to_all else self.appliesToEvents(events, verbose=True)
        )

        # Intervals are anchored to the occurrences of the events being checked
        # into, narrowed to the passed window if one is given.  Without the
        # window, a recurring event would anchor intervals to every one of its
        # occurrences.
        occ_query = EventOccurrence.objects.filter(event__in=events)
        if startTime is not None and endTime is not None:
            occ_query = occ_query.filter(endTime__gte=startTime, startTime__lte=endTime)

        intervals_by_event = {}
        for occ in occ_query:
            intervals_by_event.setdefault(occ.event_id, []).append(
                (occ.startTime, occ.endTime)
            )
        all_intervals = [x for y in intervals_by_event.values() for x in y]

        component_filters = Q(pk__isnull=True)

        for component in components:
            if applies_to_all:
                component_filters |= self.getRegistrationComponentFilters(
                    component, events=events, event_intervals=all_intervals
                )
            else:
                for event in events:
                    if per_event_applies.get(event.id):
                        component_filters |= self.getRegistrationComponentFilters(
                            component, events=[event],
                            event_intervals=intervals_by_event.get(event.id, [])
                        )

        qualifying = EventRegistration.objects.filter(
            Q(registration__final=True) & Q(cancelled=False) &
            Q(customer__isnull=False) & component_filters
        ).exclude(event__in=events)

        # Exclude anyone who is registered for one of these events themselves,
        # so that they cannot be checked in both as a registrant and as a guest.
        registeredForEvent = EventRegistration.objects.filter(
            event__in=events, cancelled=False, registration__final=True,
            customer_id=OuterRef('customer_id'),
        )

        # Where an individual has more than one qualifying registration, list
        # only the earliest one so that they appear on the list exactly once.
        firstQualifying = qualifying.filter(
            customer_id=OuterRef('customer_id')
        ).order_by('event__startTime', 'id').values('id')[:1]

        return qualifying.annotate(
            registeredForEvent=Exists(registeredForEvent)
        ).filter(
            Q(registeredForEvent=False) & Q(id=Subquery(firstQualifying))
        ).filter(filters).distinct()

    def getDescriptionForGuest(self, guest, event=None):
        '''
        Return a string that indicates the type of guest, depending on the rule
        that was used to add the guest to the list.
        '''
        if isinstance(guest, GuestListName):
            return guest.notes or gettext('Manually Added Guest')
        elif isinstance(guest, EventRegistration):
            if event and guest.event_id != event.id:
                # The guest qualifies by way of a registration for some other
                # event, under a registration-based component.
                category = getattr(getattr(guest.event, 'category', None), 'name', None)
                return gettext('Included with {category}').format(
                    category=category or gettext('registration')
                )
            return gettext('Registered')
        elif isinstance(guest, StaffMember):
            if event:
                staff_for = guest.eventstaffmember_set.filter(event=event).first()
                if staff_for:
                    return gettext(
                        'Event Staff: {category}'.format(category=staff_for.category.name)
                    )
            return gettext('Other Staff')

    def getListForEvents(
        self, events=Event.objects.none(), filters=Q(),
        includeRegistrants=True, startTime=None, endTime=None
    ):
        '''
        Get a union-ed queryset with a list of names associated with a particular event.
        Use annotations for everything to avoid potential issues with query ordering.
        '''
        if isinstance(events, list):
            events = [e for e in events if e is not None]
        names = self.guestlistname_set.annotate(
            first=F('firstName'), last=F('lastName'), contact=F('email'),
            modelType=Value('GuestListName', output_field=models.CharField()),
            guestListId=Value(self.id, output_field=models.IntegerField()),
            guestType=Case(
                When(notes__isnull=False, then=F('notes')),
                default=Value(gettext('Manually Added')),
                output_field=models.CharField()
            ),

        ).filter(filters).values(
            'id', 'first', 'last', 'contact', 'modelType', 'guestListId',
            'guestType'
        ).order_by()

        # Execute the constructed query and add the names of staff
        names = names.union(self.getStaffForEvents(events, filters, startTime=startTime, endTime=endTime).annotate(
            first=F('firstName'), last=F('lastName'), contact=F('email'),
            modelType=Value('StaffMember', output_field=models.CharField()),
            guestListId=Value(self.id, output_field=models.IntegerField()),
            guestType=Case(
                When(
                    eventstaffmember__event__in=events,
                    then=Concat(
                        Value('Event Staff: '), 'eventstaffmember__category__name'
                    )
                ),
                default=Value(gettext('Other Staff')),
                output_field=models.CharField()
            ),
        ).distinct().values(
            'id', 'first', 'last', 'contact', 'modelType', 'guestListId',
            'guestType'
        ).order_by())

        if includeRegistrants and self.includeRegistrants and events and self.appliesToEvents(events):
            names = names.union(
                EventRegistration.objects.filter(
                    filters & Q(registration__final=True) & Q(event__in=events)
                ).annotate(
                    first=F('customer__first_name'), last=F('customer__last_name'),
                    contact=F('customer__email'),
                    modelType=Value('EventRegistration', output_field=models.CharField()),
                    guestListId=Value(self.id, output_field=models.IntegerField()),
                    guestType=Value(_('Registered'), output_field=models.CharField()),
                ).values(
                    'id', 'first', 'last', 'contact', 'modelType', 'guestListId',
                    'guestType'
                ).order_by()
            )

        # Individuals admitted by way of a registration for some other event.
        if events and self.guestlistregistrationcomponent_set.all():
            names = names.union(
                self.getRegistrantsForEvents(
                    events, filters, startTime=startTime, endTime=endTime
                ).annotate(
                    first=F('customer__first_name'), last=F('customer__last_name'),
                    contact=F('customer__email'),
                    modelType=Value('EventRegistration', output_field=models.CharField()),
                    guestListId=Value(self.id, output_field=models.IntegerField()),
                    guestType=Concat(
                        Value(gettext('Included with ')),
                        Coalesce(
                            'event__series__category__name',
                            'event__publicevent__category__name',
                            Value(gettext('registration')),
                        ),
                        output_field=models.CharField()
                    ),
                ).values(
                    'id', 'first', 'last', 'contact', 'modelType', 'guestListId',
                    'guestType'
                ).order_by()
            )

        return names.order_by('last', 'first')

    def __str__(self):
        return '%s: %s' % (_('Guest list'), self.name)

    class Meta:
        ordering = ('name', )
        verbose_name = _('Guest list')
        verbose_name_plural = _('Guest lists')


class GuestListName(models.Model):
    ''' Additional names to be manually added to a particular guest list '''

    guestList = models.ForeignKey(GuestList, on_delete=models.CASCADE)
    firstName = models.CharField(_('First name'), max_length=50)
    lastName = models.CharField(_('Last name'), max_length=50)
    email = models.CharField(_('Email (optional)'), max_length=200, null=True, blank=True)

    notes = models.CharField(
        _('Notes (optional)'),
        help_text=_('These will be included on the list for reference.'),
        null=True, blank=True, max_length=200
    )

    @property
    def fullName(self):
        return ' '.join([self.firstName or '', self.lastName or ''])
    fullName.fget.short_description = _('Name')

    def __str__(self):
        return '%s: %s' % (_('Guest'), self.fullName)

    class Meta:
        ordering = ('guestList', 'lastName', 'firstName')
        verbose_name = _('Manually-added guest')
        verbose_name_plural = _('Manually added guests')
        permissions = (
            ('view_guestlist', _('Can view guest lists')),
            (
                'checkin_guests',
                _('Can check in guests using the JSON check-in view (used by door plugins)')
            )
        )


class GuestListComponentBase(models.Model):
    '''
    Abstract base class for the rules that add individuals to a guest list.
    Each subclass identifies a different set of people (staff members,
    registrants for other events, etc.), but all of them share the same notion
    of an admission rule that defines how close in time a person's
    participation must be to the event being checked into.
    '''

    guestList = models.ForeignKey(
        GuestList, verbose_name=_('Guest list'), on_delete=models.CASCADE,
        related_name='%(class)s_set'
    )

    admissionRule = models.CharField(
        _('Event admission rule'), choices=GUESTLIST_ADMISSION_CHOICES,
        max_length=10
    )

    daysBefore = models.PositiveSmallIntegerField(
        _('Days before'), null=True, blank=True,
        help_text=_(
            'For rolling admission rules only: how many days before the event '
            'being checked into the qualifying participation may occur.'
        )
    )
    daysAfter = models.PositiveSmallIntegerField(
        _('Days after'), null=True, blank=True,
        help_text=_(
            'For rolling admission rules only: how many days after the event '
            'being checked into the qualifying participation may occur.'
        )
    )

    def clean(self):
        if (
            self.admissionRule == 'Rolling' and
            self.daysBefore is None and self.daysAfter is None
        ):
            raise ValidationError(_(
                'Rolling admission rules require a number of days before ' +
                'and/or after the event.'
            ))
        super().clean()

    class Meta:
        abstract = True


class GuestListStaffComponent(GuestListComponentBase):
    ''' Add staff members to a guest list based on their staffing history. '''

    staffCategory = models.ForeignKey(
        EventStaffCategory, verbose_name=_('Category of staff members'),
        null=True, blank=True, on_delete=models.CASCADE
    )
    staffMember = models.ForeignKey(
        StaffMember, verbose_name=_('Individual staff member'),
        null=True, blank=True, on_delete=models.CASCADE
    )

    def clean(self):
        ''' Either staffCategory or staffMember must be filled in, but not both. '''
        if not self.staffCategory and not self.staffMember:
            raise ValidationError(_('Either staff category or staff member must be specified.'))
        if self.staffCategory and self.staffMember:
            raise ValidationError(_('Specify either a staff category or a staff member, not both.'))
        super().clean()

    class Meta:
        ordering = ('guestList', 'admissionRule')
        verbose_name = _('Guest list staff component')
        verbose_name_plural = _('Guest list staff components')
        unique_together = ('guestList', 'staffCategory', 'staffMember')


class GuestListRegistrationComponent(GuestListComponentBase):
    '''
    Add customers to a guest list because they are registered for some other
    event.  This is used where registration for one event also includes
    admission to another, such as a class series that includes admission to a
    social dance, without selling the two together or generating a second
    EventRegistration.
    '''

    admissionRule = models.CharField(
        _('Event admission rule'), choices=GUESTLIST_REGISTRATION_ADMISSION_CHOICES,
        max_length=10
    )

    seriesCategories = models.ManyToManyField(
        SeriesCategory, verbose_name=_('Qualifying series categories'), blank=True,
        help_text=_(
            'Registration for a class series in one of these categories admits '
            'the customer to events on this guest list.'
        )
    )
    eventCategories = models.ManyToManyField(
        PublicEventCategory, verbose_name=_('Qualifying public event categories'),
        blank=True,
        help_text=_(
            'Registration for a public event in one of these categories admits '
            'the customer to events on this guest list.'
        )
    )

    # Note that the requirement of at least one qualifying category is enforced
    # by the admin form rather than by clean(), because the categories are
    # many-to-many fields whose submitted values are not yet available when
    # model validation runs.  A component with no categories admits no one.

    class Meta:
        ordering = ('guestList', 'admissionRule')
        verbose_name = _('Guest list registration component')
        verbose_name_plural = _('Guest list registration components')
