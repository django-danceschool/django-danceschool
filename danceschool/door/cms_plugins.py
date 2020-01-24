from django.utils.translation import ugettext_lazy as _
from django.utils import timezone
from django.middleware.csrf import get_token
from django.contrib.admin import TabularInline

from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from cms.models.pluginmodel import CMSPlugin

from datetime import datetime, timedelta
from collections import OrderedDict
from adminsortable2.admin import SortableInlineAdminMixin

from .models import DoorRegisterEventPluginModel, DoorRegisterEventPluginChoice
from danceschool.core.models import (
    StaffMemberListPluginModel, LocationPluginModel, LocationListPluginModel,
    EventListPluginModel, StaffMember, Instructor, Event, Series, PublicEvent,
    Location
)
from danceschool.core.mixins import PluginTemplateMixin
from danceschool.core.utils.timezone import ensure_localtime


class DoorRegisterEventChoiceInline(SortableInlineAdminMixin, TabularInline):
    model = DoorRegisterEventPluginChoice
    min_num = 1
    extra = 1
    fields = [
        'optionType', 'optionLabel', 'optionLocation',
        ('byRole', 'byPaymentMethod',),
        ('requireFullRegistration', 'registrationOpenDisplay', 'soldOutRule'),
        'voucherId', 'data'
    ]


class DoorRegisterVoucherPlugin(CMSPluginBase):
    name = _('Register: Voucher Entry')
    cache = True
    module = _('Door Register')
    render_template = 'door/register/door_voucher.html'


class DoorRegisterGuestSearchPlugin(CMSPluginBase):
    name = _('Register: Customer/Guest Search')
    cache = True
    module = _('Door Register')
    render_template = 'door/register/door_guest_search.html'


class DoorRegisterEventPlugin(PluginTemplateMixin, CMSPluginBase):
    model = DoorRegisterEventPluginModel
    name = _('Register: Events at the door')
    cache = False
    module = _('Door Register')
    render_template = 'door/register/event_register.html'
    inlines = [DoorRegisterEventChoiceInline, ]

    fieldsets = (
        (None, {
            'fields': (
                'title', 'eventType', 'occursWithinDays', 'registrationOpenLimit',
                'requireFullRegistration', 'paymentMethods',
            )
        }),
        (_('Limit Start Date'), {
            'classes': ('collapse',),
            'fields': ('limitTypeStart', 'daysStart', 'startDate'),
        }),
        (_('Limit End Date'), {
            'classes': ('collapse',),
            'fields': ('limitTypeEnd', 'daysEnd', 'endDate'),
        }),
        (_('Limit Number'), {
            'classes': ('collapse',),
            'fields': ('limitNumber', 'sortOrder'),
        }),
        (_('Other Limit Restrictions'), {
            'classes': ('collapse',),
            'fields': ('eventCategories', 'seriesCategories', 'levels', 'location', 'weekday'),
        }),
        (_('Display Options'), {
            'classes': ('collapse',),
            'fields': ('template', 'cssClasses'),
        }),
    )

    def render(self, context, instance, placeholder):
        context = super().render(context, instance, placeholder)

        # Ensure that the CSRF protection cookie is set for all lists of events.
        # Useful for things like buttons that go directly into the registration process.
        get_token(context.get('request'))

        listing = context.get('allEvents', Event.objects.none())
        today_start = ensure_localtime(
            context.get('today', timezone.now())
        ).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Filter on event type (Series vs. PublicEvent)
        if instance.eventType == 'S':
            listing = listing.instance_of(Series)
        elif instance.eventType == 'P':
            listing = listing.instance_of(PublicEvent)

        filters = {}

        # Filter on event start and/or end times
        startKey = 'endTime__gte'
        endKey = 'startTime__lte'

        if instance.limitTypeStart == 'S':
            startKey = 'startTime__gte'
        if instance.limitTypeEnd == 'E':
            endKey = 'endTime__lte'

        if instance.startDate:
            filters[startKey] = datetime.combine(instance.startDate, datetime.min.time())
        elif instance.daysStart is not None:
            filters[startKey] = timezone.now() + timedelta(days=instance.daysStart)

        if instance.endDate:
            filters[endKey] = datetime.combine(instance.endDate, datetime.max.time())
        elif instance.daysEnd is not None:
            filters[endKey] = timezone.now() + timedelta(days=instance.daysEnd)

        # Filter on event occurrence time (relative to the current date, in local time)
        if instance.occursWithinDays is not None:
            filters['eventoccurrence__endTime__gte'] = today_start
            filters['eventoccurrence__startTime__lte'] = today_start + timedelta(
                days=1 + instance.occursWithinDays
            )

        # Filter on open or closed registrations
        if instance.registrationOpenLimit == 'O':
            filters['registrationOpen'] = True
        elif instance.registrationOpenLimit == 'C':
            filters['registrationOpen'] = False

        # Filter on location
        if instance.location.all():
            filters['location__in'] = instance.location.all()

        # Filter on category
        if instance.eventCategories.all():
            filters['publicevent__category__in'] = instance.eventCategories.all()

        if instance.seriesCategories.all():
            filters['series__category__in'] = instance.seriesCategories.all()

        # Filter on class level (for Series only)
        if instance.levels.all():
            filters['series__classDescription__danceTypeLevel__in'] = instance.levels.all()

        # Filter on weekday
        # Python calendar module indexes weekday differently from Django
        if instance.weekday is not None:
            filters['startTime__week_day'] = (instance.weekday + 2) % 7

        order_by = '-startTime' if instance.sortOrder == 'D' else 'startTime'
        listing = listing.filter(**filters).order_by(order_by).distinct()[:instance.limitNumber]

        # Create an ordered dictionary of choices with all the information needed
        # for the page to render and Ajax processing to occur.
        register_choices = OrderedDict()

        # Construct a list of payment methods and associated registration rules
        # for the choices in this plugin.  If no payment methods are specified,
        # the addChoices() method will use a default.
        paymentMethods = [
            {
                'name': x.name,
                'requireFullRegistration': x.requireFullRegistration,
                'autoSubmit': x.allowAutoSubmit,
            } for x in instance.paymentMethods.all()
        ]

        # Each event gets its own list of choices.
        for event in listing:

            primary_options = []
            additional_options = []

            for choiceRule in instance.doorregistereventpluginchoice_set.all():
                new_primary_options, new_additional_options = choiceRule.addChoices(
                    event, requireFullRegistration=instance.requireFullRegistration,
                    paymentMethods=paymentMethods,
                )
                primary_options += new_primary_options
                additional_options += new_additional_options

            register_choices[event.id] = {
                'event': event,
                'primary_options': primary_options,
                'additional_options': additional_options,
            }

        context.update({
            'event_list': listing,
            'register_choices': register_choices,
        })
        return context


plugin_pool.register_plugin(DoorRegisterVoucherPlugin)
plugin_pool.register_plugin(DoorRegisterGuestSearchPlugin)
plugin_pool.register_plugin(DoorRegisterEventPlugin)
