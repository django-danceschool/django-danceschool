from django.db import models
from django.db.models import Q, OuterRef, Subquery
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from calendar import day_name
from datetime import datetime, timedelta
from math import ceil

from cms.models.pluginmodel import CMSPlugin
import logging

from ..utils.timezone import ensure_localtime

logger = logging.getLogger(__name__)


class RegisterEventLimitedModel(CMSPlugin):
    '''
    Abstract base class for CMS plugin models that expose a configurable,
    filtered subset of events.  Provides date-range, occurrence-window,
    registration-status, location, category, level and weekday filters, plus
    optional automatic check-in behaviour.

    Concrete subclasses live in both danceschool.core (public-register plugins)
    and danceschool.register (at-the-door register plugins).
    '''
    LIMIT_CHOICES = [
        ('S', _('Event start date')),
        ('E', _('Event end date')),
    ]
    EVENT_TYPE_CHOICES = [
        ('B', _('Class Series and Public Events')),
        ('S', _('Only Class Series')),
        ('P', _('Only Public Events')),
    ]
    OPEN_CHOICES = [
        ('O', _('Open for registration only')),
        ('C', _('Closed for registration only')),
        ('B', _('Both open and closed events')),
    ]
    SORT_CHOICES = [
        ('A', _('Ascending')),
        ('D', _('Descending')),
    ]
    AUTO_CHECKIN_CHOICES = [
        ('0', _('No automatic check-in')),
        ('E', _('Current event occurrence (next ending time)')),
        ('S', _('Current event occurrence (next starting time)')),
        ('F', _('Entire event')),
    ]

    eventType = models.CharField(
        _('Limit to event type'), max_length=1, choices=EVENT_TYPE_CHOICES,
        default='B'
    )
    limitNumber = models.PositiveSmallIntegerField(
        _('Limit number'), help_text=_('Leave blank for no restriction'),
        null=True, blank=True
    )
    sortOrder = models.CharField(
        _('Sort by start time'), max_length=1, choices=SORT_CHOICES, default='A',
        help_text=_('This may be overridden by the particular template in use')
    )

    occursWithinDays = models.PositiveSmallIntegerField(
        _('Event occurs within __ days'), null=True, blank=True, default=0,
        help_text=_(
            'If set, then the register will only include events that have an '
            'occurrence within this many days in the future of the register date'
            '(usually) the current date. The default of 0 limits to only events '
            'that occur on the register date. Leave blank for no restriction.'
        ),
    )

    limitTypeStart = models.CharField(
        _('Limit interval start by'), max_length=1, choices=LIMIT_CHOICES, default='E'
    )
    daysStart = models.SmallIntegerField(
        _('Interval limited to __ days from present'), null=True, blank=True,
        help_text=_(
            '(E.g. enter -30 for an interval that starts with 30 days prior to today)'
            ' Leave blank for no limit, or enter 0 to limit to future events'
        )
    )
    startDate = models.DateField(
        _('Exact interval start date'), null=True, blank=True,
        help_text=_('Leave blank for no limit (overrides relative interval limits)')
    )

    limitTypeEnd = models.CharField(
        _('Limit interval end by'), max_length=1, choices=LIMIT_CHOICES, default='S'
    )
    daysEnd = models.SmallIntegerField(
        _('Interval limited to __ days from present'), null=True, blank=True,
        help_text=_(
            '(E.g. enter 30 for an interval that ends 30 days from today) '
            'Leave blank for no limit, or enter 0 to limit to past events'
        )
    )
    endDate = models.DateField(
        _('Exact interval end date '), null=True, blank=True,
        help_text=_('Leave blank for no limit (overrides relative interval limits)')
    )

    registrationOpenLimit = models.CharField(
        _('Limit to open/closed for registration only'), max_length=1,
        choices=OPEN_CHOICES, default='O'
    )

    location = models.ManyToManyField(
        'core.Location', verbose_name=_('Limit to locations'),
        help_text=_('Leave blank for no restriction'), blank=True
    )

    weekday = models.PositiveSmallIntegerField(
        _('Limit to weekday'), null=True, blank=True,
        choices=[(x, _(day_name[x])) for x in range(0, 7)]
    )

    eventCategories = models.ManyToManyField(
        'core.PublicEventCategory', verbose_name=_('Limit to public event categories'),
        help_text=_('Leave blank for no restriction'),
        blank=True
    )

    seriesCategories = models.ManyToManyField(
        'core.SeriesCategory', verbose_name=_('Limit to series categories'),
        help_text=_('Leave blank for no restriction'),
        blank=True
    )

    levels = models.ManyToManyField(
        'core.DanceTypeLevel', verbose_name=_('Limit to type and levels'),
        help_text=_('Leave blank for no restriction'),
        blank=True
    )

    autoCheckIn = models.CharField(
        _('Automatic event/occurrence check-in when registration is complete'),
        max_length=1, choices=AUTO_CHECKIN_CHOICES, default='E'
    )

    def getEvents(self, dateTime=None, initial=None):
        '''
        Return the set of events that match the parameters specified by this
        model instance, optionally limited to a particular date or to a subset
        of an initial listing.
        '''
        from django.db.models.query import QuerySet
        from .event_base import Event
        from .event_occurrences import EventOccurrence
        from .event_types import Series, PublicEvent

        if initial and isinstance(initial, QuerySet):
            listing = initial
        else:
            listing = Event.objects.all()

        # Filter on event type (Series vs. PublicEvent)
        if self.eventType == 'S':
            listing = listing.instance_of(Series)
        elif self.eventType == 'P':
            listing = listing.instance_of(PublicEvent)

        # filters are used only on events; time_filters on both events and
        # occurrences; occ_filters on occurrences only.
        filters = {}
        time_filters = {}
        occ_filters = {'event': OuterRef('pk')}

        # Avoid potential issues with comparing offset-naive and offset-aware datetimes.
        dateTime = ensure_localtime(dateTime)

        # Filter on event start and/or end times
        startKey = 'endTime__gte'
        endKey = 'startTime__lte'

        if self.limitTypeStart == 'S':
            startKey = 'startTime__gte'
        if self.limitTypeEnd == 'E':
            endKey = 'endTime__lte'

        if self.startDate:
            time_filters[startKey] = datetime.combine(self.startDate, datetime.min.time())
        elif self.daysStart is not None:
            time_filters[startKey] = timezone.now() + timedelta(days=self.daysStart)

        if self.endDate:
            time_filters[endKey] = datetime.combine(self.endDate, datetime.max.time())
        elif self.daysEnd is not None:
            time_filters[endKey] = timezone.now() + timedelta(days=self.daysEnd)

        # Filter on event occurrence time (relative to the current date, in local time)
        if self.occursWithinDays is not None and dateTime:
            window_start = dateTime
            window_end = dateTime + timedelta(days=1 + self.occursWithinDays)

            filters['eventoccurrence__endTime__gte'] = window_start
            filters['eventoccurrence__startTime__lte'] = window_end
            occ_filters['endTime__gte'] = window_start
            occ_filters['startTime__lte'] = window_end

            # If multiple occurrences fall within the window, limit further so
            # that check-in happens on the first upcoming occurrence.  We build
            # in a 15-minute grace period.
            now = ensure_localtime(datetime.now())
            if now >= window_start and now <= window_end:
                occ_filters['endTime__gte'] = now - timedelta(minutes=15)

        # Filter on open or closed registrations
        if self.registrationOpenLimit == 'O':
            filters['registrationOpen'] = True
        elif self.registrationOpenLimit == 'C':
            filters['registrationOpen'] = False

        # Filter on location
        if self.location.all():
            filters['location__in'] = self.location.all()

        # Filter on category
        if self.eventCategories.all():
            filters['publicevent__category__in'] = self.eventCategories.all()

        if self.seriesCategories.all():
            filters['series__category__in'] = self.seriesCategories.all()

        # Filter on class level (for Series only)
        if self.levels.all():
            filters['series__classDescription__danceTypeLevel__in'] = self.levels.all()

        # Filter on weekday
        # Python calendar module indexes weekday differently from Django
        if self.weekday is not None:
            filters['startTime__week_day'] = (self.weekday + 2) % 7

        if self.autoCheckIn == 'S':
            occ_order_by = 'startTime'
        else:
            occ_order_by = 'endTime'

        order_by = '-startTime' if self.sortOrder == 'D' else 'startTime'
        listing = listing.annotate(
            thisOccurrence=Subquery(EventOccurrence.objects.filter(
                **occ_filters, **time_filters,
            ).order_by(occ_order_by).values('id')[:1])
        ).filter(
            **filters, **time_filters).order_by(order_by).prefetch_related(
                'eventoccurrence_set'
            ).distinct()[:self.limitNumber]
        return listing

    def copy_relations(self, oldinstance):
        self.location.set(oldinstance.location.all())
        self.eventCategories.set(oldinstance.eventCategories.all())
        self.seriesCategories.set(oldinstance.seriesCategories.all())
        self.levels.set(oldinstance.levels.all())

    class Meta:
        abstract = True


class PublicRegisterNavPluginModel(CMSPlugin):
    '''
    Model for the public register navigation bar plugin.  The plugin renders
    a sticky Bootstrap navbar whose links are populated by JavaScript after
    page load by reading the data-section-title attributes of
    .public-register-section elements (produced by PublicRegisterEventPlugin).

    No sections are stored here; this is purely a display/UX plugin.
    '''

    title = models.CharField(
        _('Navbar brand text'), max_length=200, blank=True, default='',
        help_text=_(
            'Optional text displayed at the left edge of the navbar. '
            'Leave blank to show navigation links only.'
        )
    )

    def __str__(self):
        return self.title or str(_('Public register navigation bar'))

    class Meta:
        verbose_name = _('Public register navigation bar')
        verbose_name_plural = _('Public register navigation bars')


class PublicRegisterEventPluginModel(RegisterEventLimitedModel):
    '''
    CMS plugin model for the public-facing registration page.  Provides
    filterable event listings without at-the-door-specific options (payment
    methods, requireFullRegistration, autoCheckIn).
    '''

    title = models.CharField(
        _('Section title'), max_length=250, default=_('Upcoming Events'), blank=True
    )

    cssClasses = models.CharField(
        _('Custom CSS classes'), max_length=250, null=True, blank=True,
        help_text=_('Classes are applied to the surrounding &lt;div&gt;')
    )

    template = models.CharField(
        _('Plugin template'), max_length=250, null=True, blank=True
    )

    def copy_relations(self, oldinstance):
        super().copy_relations(oldinstance)
        self.publicregistereventpluginchoice_set.all().delete()
        for choice in oldinstance.publicregistereventpluginchoice_set.all():
            choice.pk = None
            choice.eventPlugin = self
            choice.save()

    def get_short_description(self):
        return self.title or self.id

    def save(self, *args, **kwargs):
        needs_default_choice = (
            not self.publicregistereventpluginchoice_set.exists() if self.pk else True
        )
        super().save(*args, **kwargs)
        if needs_default_choice:
            PublicRegisterEventPluginChoice.objects.create(eventPlugin=self)

    class Meta:
        permissions = (
            (
                'choose_custom_public_plugin_template',
                _('Can enter a custom plugin template for public register plugins.')
            ),
        )


class PublicRegisterEventPluginChoice(models.Model):
    '''
    Configuration for how PublicRegisterEventPluginModel renders registration
    inputs.  Each instance produces a labelled number input per available role
    (or a single "General admission" input when no roles are defined).
    '''

    SOLDOUT_CHOICES = [
        ('D', _('Display with sold-out label')),
        ('H', _('Hide sold-out choices')),
    ]

    eventPlugin = models.ForeignKey(
        PublicRegisterEventPluginModel,
        verbose_name=_('Plugin'),
        on_delete=models.CASCADE,
    )

    optionLabel = models.CharField(
        _('Label prefix'), max_length=100, blank=True, default='',
        help_text=_(
            'Optional prefix shown before the role name, e.g. "Sign up as". '
            'Leave blank to show only the role name.'
        )
    )

    soldOutRule = models.CharField(
        _('Rule for sold-out choices'), max_length=1, default='D',
        choices=SOLDOUT_CHOICES,
    )

    data = models.JSONField(
        _('Additional data attached to registrations'), default=dict, blank=True,
        help_text=_(
            'Custom JSON stored with each registration produced by this choice. '
            'This value is kept server-side and is never transmitted through '
            'the browser, so it cannot be modified by users.'
        )
    )

    order = models.PositiveSmallIntegerField(default=0, blank=False, null=False)

    def addChoices(self, event):
        '''
        Return a list of choice dicts for the given event — one entry per
        available role, or a single "General admission" entry when the event
        has no roles defined.
        '''
        from math import ceil
        from .event_types import Series
        from django.db.models import Count

        choices = []

        event_roles = list(
            event.eventrole_set.filter(capacity__gt=0).select_related('role')
        )

        if event_roles:
            roles_data = [
                {'name': er.role.name, 'id': er.role.id, 'capacity': er.capacity}
                for er in event_roles
            ]
        elif isinstance(event, Series):
            try:
                dtype_roles = list(
                    event.classDescription.danceTypeLevel.danceType.roles.all()
                )
            except Exception:
                dtype_roles = []
            if dtype_roles:
                per_role_cap = ceil(event.capacity / len(dtype_roles))
                roles_data = [
                    {'name': r.name, 'id': r.id, 'capacity': per_role_cap}
                    for r in dtype_roles
                ]
            else:
                roles_data = []
        else:
            roles_data = []

        if roles_data:
            count_rows = event.eventregistration_set.filter(
                cancelled=False, dropIn=False, registration__final=True
            ).values('role_id').annotate(count=Count('id'))
            count_map = {row['role_id']: row['count'] for row in count_rows}
        else:
            roles_data = [{'name': None, 'id': None, 'capacity': event.capacity}]
            count_map = {None: event.eventregistration_set.filter(
                cancelled=False, dropIn=False, registration__final=True
            ).count()}

        for i, role in enumerate(roles_data):
            num_registered = count_map.get(role['id'], 0)
            capacity = role['capacity'] or 0
            sold_out = num_registered >= capacity

            if sold_out and self.soldOutRule == 'H':
                continue

            label = ' '.join(filter(None, [
                self.optionLabel,
                role['name'] or str(_('General admission')),
            ]))

            choices.append({
                'label': label,
                'price': event.pricingTier.onlinePrice if event.pricingTier else 0,
                'roleName': role['name'],
                'roleId': role['id'],
                'numRegistered': num_registered,
                'capacity': capacity,
                'soldOut': sold_out,
                'choiceId': 'pubchoice_{}_{}_{}'.format(event.id, self.id, i),
            })

        return choices

    class Meta:
        ordering = ['order']
