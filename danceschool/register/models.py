from django.db import models
from django.db.models import Value, OuterRef, Subquery
from django.db.models.query import QuerySet
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from calendar import day_name
import logging
import json
from datetime import datetime, timedelta

from cms.models.pluginmodel import CMSPlugin
from cms.models.fields import PlaceholderField

from danceschool.core.models import (
    Event, SeriesCategory, PublicEventCategory, Location, DanceTypeLevel,
    PublicEvent, Series, EventOccurrence
)
from danceschool.core.utils.timezone import ensure_localtime

# Define logger for this file
logger = logging.getLogger(__name__)


class Register(models.Model):
    '''
    An organization may require more than one at-the-door register page, depending on its needs.
    Each instance of this model provides a separate CMS placeholder for an at-the-door register.
    '''

    title = models.CharField(
        _('Register title'),
        help_text=_(
            'Since there may be more than one at-the-door registration page, give each one a title '
        ),
        max_length=200,
    )

    slug = models.SlugField(
        _('Slug'),
        max_length=50,
        help_text=_('Register pages are accessed by a URL based on this slug.'),
    )

    enabled = models.BooleanField(
        _('Enable this register page'), default=True, blank=True
    )

    placeholder = PlaceholderField('register_placeholder')

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = _('At-the-door register')
        verbose_name_plural = _('At-the-door registers')
        ordering = ('title',)


class RegisterPaymentMethod(models.Model):
    '''
    At the door, it is often desirable to have separate buttons for different potential
    payment methods, and different registration logic for each (e.g. cash vs. credit).
    Each instance of the RegisterEventPluginModel can optionally specify the
    particular instances of this model (payment methods) that have separate buttons.
    '''

    name = models.CharField(_('Method name'), max_length=50)

    requireFullRegistration = models.BooleanField(
        _('Is full registration (name and email) always required for this method?'),
        default=False,
        help_text=_(
            'If checked, then whenever this payment method is used, the ' +
            'student information form will be required. The full registration ' +
            'process may also be required by a particular register plugin ' +
            'or registration choice.'
        )
    )

    allowAutoSubmit = models.BooleanField(
        _('Auto-submission'),
        default=False,
        help_text=_(
            'If the payatdoor app is enabled, this setting can be used to ' +
            'permit automatic recording of non-electronic door payments to ' +
            'speed the registration process. ' +
            'For auto-submission to work, the name of this payment method ' +
            'must match the name of a payment method in the setting ' +
            'ATTHEDOOR_PAYMENTMETHOD_CHOICES for the payatdoor app. ' +
            'Valid defaults are Cash and Check.'
        ),
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Payment method')
        verbose_name_plural = _('Payment methods')
        ordering = ('name',)


class RegisterEventLimitedModel(CMSPlugin):
    '''
    This is an abstract base class for models that need to provide a limited
    set of events.
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
            'If set, then the register will only include events that have an ' +
            'occurrence within this many days in the future of the register date' +
            '(usually) the current date. The default of 0 limits to only events ' +
            'that occur on the register date. Leave blank for no restriction.'
        ),
    )

    limitTypeStart = models.CharField(
        _('Limit interval start by'), max_length=1, choices=LIMIT_CHOICES, default='E'
    )
    daysStart = models.SmallIntegerField(
        _('Interval limited to __ days from present'), null=True, blank=True,
        help_text=_(
            '(E.g. enter -30 for an interval that starts with 30 days prior to today)' +
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
            '(E.g. enter 30 for an interval that ends 30 days from today) ' +
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
        Location, verbose_name=_('Limit to locations'),
        help_text=_('Leave blank for no restriction'), blank=True
    )

    weekday = models.PositiveSmallIntegerField(
        _('Limit to weekday'), null=True, blank=True,
        choices=[(x, _(day_name[x])) for x in range(0, 7)]
    )

    eventCategories = models.ManyToManyField(
        PublicEventCategory, verbose_name=_('Limit to public event categories'),
        help_text=_('Leave blank for no restriction'),
        blank=True
    )

    seriesCategories = models.ManyToManyField(
        SeriesCategory, verbose_name=_('Limit to series categories'),
        help_text=_('Leave blank for no restriction'),
        blank=True
    )

    levels = models.ManyToManyField(
        DanceTypeLevel, verbose_name=_('Limit to type and levels'),
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
        if initial and isinstance(initial, QuerySet):
            listing = initial
        else:
            listing = Event.objects.all()

        # Filter on event type (Series vs. PublicEvent)
        if self.eventType == 'S':
            listing = listing.instance_of(Series)
        elif self.eventType == 'P':
            listing = listing.instance_of(PublicEvent)

        # Filters are used only to filter events.  time_filters are used to
        # filter both events and occurrences.  occ_filters are used to filter
        # only occurrences in the next occurrence subquery.
        filters = {}
        time_filters = {}
        occ_filters = {'event': OuterRef('pk')}

        # Avoid potential issues with comparing offset-naive and offset-aware
        # datetimes.
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

            # If multiple occurrences fall within the window, this limits the
            # filter on occupations further so that check-in happens on the
            # first upcoming occurrence.  We build in a 15 minute grace period.
            # If your event has back-to-back occurrences, you may need separate
            # choices for each occurrence to avoid complications in tracking
            # check-ins.
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

        # If automatic occurrence check-in is specified, return the ID of the
        # next eligible occurrence for each 
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


class RegisterEventPluginModel(RegisterEventLimitedModel):
    '''
    This model is typically used to configure upcoming event listings, but it can
    be customized to a variety of purposes using custom templates, etc.
    '''

    title = models.CharField(
        _('Custom list title'), max_length=250, default=_('Upcoming Events'),
        blank=True
    )

    cssClasses = models.CharField(
        _('Custom CSS classes'), max_length=250, null=True, blank=True,
        help_text=_('Classes are applied to surrounding &lt;div&gt;')
    )
    template = models.CharField(_('Plugin template'), max_length=250, null=True, blank=True)

    requireFullRegistration = models.BooleanField(
        _('Require full registration'), blank=True, default=True,
        help_text=_(
            'If checked, then the user will be sent to the second page of the ' +
            'registration process to provide name and email. Particular payment ' +
            'methods may also require the full registration process.'
        )
    )

    paymentMethods = models.ManyToManyField(
        RegisterPaymentMethod,
        verbose_name=_('Payment Methods'),
        help_text=_(
            'If you would like separate buttons for individual payment methods, ' +
            'then select them here.  If left blank, a single button will be shown ' +
            'and no payment method will be specified.'
        ),
        blank=True,
    )

    def copy_relations(self, oldinstance):
        super().copy_relations(oldinstance)

        # Delete existing choice instances to avoid duplicates, then duplicate
        # choice instances from the old plugin instance.  Following Django CMS
        # documentation.
        self.registereventpluginchoice_set.all().delete()

        for choice in oldinstance.registereventpluginchoice_set.all():
            choice.pk = None
            choice.eventPlugin = self
            choice.save()

    def get_short_description(self):
        desc = self.title or ''
        choices = getattr(self.get_plugin_class(), 'template_choices', [])
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

    def save(self, *args, **kwargs):
        '''
        New plugin instances have, by default, the standard registration buttons
        broken out by role and nothing else.
        '''

        created = not self.pk
        super().save(*args, **kwargs)
        if created:
            RegisterEventPluginChoice.objects.create(
                eventPlugin=self,
            )

    class Meta:
        permissions = (
            (
                'choose_custom_plugin_template',
                _('Can enter a custom plugin template for plugins with selectable template.')
            ),
        )


class RegisterGuestSearchPluginModel(RegisterEventLimitedModel):
    '''
    For checking in guests, we need to limit the set of events that they
    may be checked into.  This doesn't need anything more than general event
    limitations.
    '''
    pass


class RegisterEventPluginChoice(models.Model):
    '''
    Individual register sections may have custom rules for the types and display
    of options that they permit.  This sortable model holds rules for the type
    of additional options that are enabled within each instance of
    RegisterEventPluginModel.
    '''
    OPTION_TYPE_CHOICES = [
        ('G', _('Standard registration')),
        ('D', _('Register as a drop-in')),
        ('S', _('Register with student designation')),
    ]
    OPTION_LOCATION_CHOICES = [
        ('P', _('Primary choice')),
        ('A', _('Additional choice')),
    ]
    OPEN_CHOICES = [
        ('O', _('Open for registration only')),
        ('C', _('Closed for registration only')),
        ('B', _('Both open and closed events')),
    ]
    SOLDOUT_CHOICES = [
        ('D', _('Display with label')),
        ('A', _('Move to additional choice drop-down')),
        ('H', _('Hide sold out choices')),
    ]

    eventPlugin = models.ForeignKey(
        RegisterEventPluginModel,
        verbose_name=_('Plugin'),
        on_delete=models.CASCADE,
    )

    optionType = models.CharField(
        _('Option type'), max_length=1, choices=OPTION_TYPE_CHOICES,
        default='G',
    )

    optionLabel = models.CharField(
        _('Override option label'), max_length=100, null=True, blank=True,
        help_text=_('Leave blank for default labeling to be applied.')
    )

    optionLocation = models.CharField(
        _('Option location'), max_length=1, choices=OPTION_LOCATION_CHOICES,
        default='P',
        help_text=_(
            'By default, primary choices receive their own button, while ' +
            'additional choices are included in a drop-down menu.'
        )
    )

    byRole = models.BooleanField(
        _('Separate choices for each role'), blank=True, default=True,
        help_text=_(
            'If disabled, then this option will not be broken out by role. ' +
            'It is not recommended to do this except for drop-in ' +
            'registrations, because the default registration workflow does ' +
            'not allow for later selection of roles.'
        )
    )

    byPaymentMethod = models.BooleanField(
        _('Separate choices for each payment method'), blank=True, default=False,
        help_text=_(
            'If enabled, then this option will be broken out by the payment ' +
            'methods specified for this plugin. If no payment methods are ' +
            'specified, then this choice will have no effect. It is useful to ' +
            'enable this option when different payment methods require ' +
            'different registration logic.'
        )
    )

    requireFullRegistration = models.BooleanField(
        _('Require full registration'), blank=True, default=True,
        help_text=_(
            'If checked, then the user will be sent to the second page of the ' +
            'registration process to provide name and email. Particular payment ' +
            'methods or plugins may also require the full registration process ' +
            'and can override this option.'
        )
    )

    registrationOpenDisplay = models.CharField(
        _('Display if open/closed for registration only'), max_length=1,
        choices=OPEN_CHOICES, default='B'
    )

    soldOutRule = models.CharField(
        _('Rule for sold out choices'), max_length=1, default='D',
        choices=SOLDOUT_CHOICES,
    )

    voucherId = models.CharField(
        _('Optional voucher code to be added simultaneously'),
        max_length=100, null=True, blank=True
    )

    data = models.JSONField(
        _('Additional data passed with registration'), default=dict, blank=True,
        help_text=_(
            'This may be used for passing specific information about this ' +
            'event registration for statistical or other custom purposes.'
        )
    )

    order = models.PositiveSmallIntegerField(default=0, blank=False, null=False)

    def getDefaultLabel(self):
        if self.optionLabel:
            return self.optionLabel
        elif self.optionType == 'D':
            return _('Drop-in')
        elif self.optionType == 'S':
            return _('Student')
        elif self.voucherId:
            return _('Register with voucher {}'.format(self.voucherId))
        return _('Register')

    def addChoices(self, event, requireFullRegistration=True, paymentMethods=None):
        '''
        This method handles the logic of creating one or more choices (i.e. buttons)
        associated with this instance for a particular event.  The exact number
        of choices and the passed attributes in each will depend on the options
        for this instance.  The method returns a list of primary and additional
        options that are collected by the plugin's render() method and sent to
        the template for display.
        '''
        primary_options = []
        additional_options = []

        # No need to continue if the event open status does not match the choice
        # requirements.
        if (
            (event.registrationOpen is False and self.registrationOpenDisplay == "O") or
            (event.registrationOpen is True and self.registrationOpenDisplay == "C")
        ):
            return (primary_options, additional_options)

        # Create generic payment method if we don't have or need specific
        # payment methods.
        if not paymentMethods or not self.byPaymentMethod:
            paymentMethods = [
                {
                    'name': None,
                    'requireFullRegistration': False,
                    'autoSubmit': False,
                },
            ]
        roles = [
            {
                'name': x.name,
                'id': x.id,
                'soldOut': event.soldOutForRole(x),
            } for x in event.availableRoles
        ]
        if not roles or not self.byRole:
            roles = [{'name': None, 'id': None, 'soldOut': event.soldOut}, ]

        # Used to populate the unique choice ID
        choice_counter = 0

        for role in roles:
            if role['soldOut'] and self.soldOutRule == 'H':
                continue

            for method in paymentMethods:

                requireFullRegistration = (
                    self.requireFullRegistration or
                    method['requireFullRegistration'] or
                    requireFullRegistration
                )

                soldOutString = '({})'.format(_('Sold out')) if role['soldOut'] else ''

                this_label = '{} {} {} {}'.format(
                    self.getDefaultLabel() or '',
                    role['name'] or '',
                    method['name'] or '',
                    soldOutString or '',
                ).strip()

                this_choice = {
                        'label': this_label,
                        'price': event.pricingTier.doorPrice,
                        'roleName': role['name'],
                        'roleId': role['id'],
                        'paymentMethod': method['name'],
                        'requireFullRegistration': requireFullRegistration,
                        'autoSubmit': method['autoSubmit'],
                        'choiceId': 'eventchoice_{}_{}_{}'.format(
                            event.id, self.id, choice_counter
                        )
                }

                # Add additional data needed for vouchers, drop-ins, students,
                # and comped registrations
                if self.optionType == 'D':
                    this_choice.update({
                        'dropIn': True, 'price': event.pricingTier.dropinPrice,
                        'dropInOccurrence': getattr(event, 'thisOccurrence', None),
                    })
                if self.voucherId:
                    this_choice.update({'voucherId': self.voucherId})
                if self.optionType == 'S':
                    this_choice.update({'student': True})
                if self.eventPlugin.autoCheckIn in ['S', 'E']:
                    this_choice.update({
                        'checkInOccurrence': getattr(event, 'thisOccurrence', None)
                    })

                # Add additional data passed via the JSON field.  This is encoded as
                # JSON since the output will be added as a data attribute by a template.
                if self.data:
                    this_choice.update({'data': json.dumps(self.data)})

                # Sold out options that should be hidden haven't gotten this far,
                # so everything else is placed appropriately here.
                if (self.optionLocation == 'P' and not (
                    role['soldOut'] and self.soldOutRule == 'A'
                )):
                    primary_options.append(this_choice)
                    choice_counter += 1
                else:
                    additional_options.append(this_choice)
                    choice_counter += 1

        return (primary_options, additional_options)

    class Meta(object):
        ordering = ['order', ]
