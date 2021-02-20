from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.middleware.csrf import get_token
from django.contrib.admin import TabularInline

from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool

from collections import OrderedDict
from adminsortable2.admin import SortableInlineAdminMixin

from .models import (
    DoorRegisterEventPluginModel, DoorRegisterEventPluginChoice,
    DoorRegisterGuestSearchPluginModel
)
from danceschool.core.models import Event
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
    model = DoorRegisterGuestSearchPluginModel
    name = _('Register: Customer/Guest Search')
    cache = True
    module = _('Door Register')
    render_template = 'door/register/door_guest_search.html'

    fieldsets = (
        (None, {
            'fields': (
                'eventType', 'occursWithinDays', 'registrationOpenLimit',
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
    )

    def render(self, context, instance, placeholder):
        context = super().render(context, instance, placeholder)

        today_start = ensure_localtime(
            context.get('today', timezone.now())
        ).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        context.update({
            'event_list': instance.getEvents(
                dateTime=today_start,
                initial=context.get('allEvents', Event.objects.none())
            ).values_list('id', flat=True),
            'checkin_guests': context['request'].user.has_perm('guestlist.checkin_guests')
        })

        return context


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

        today_start = ensure_localtime(
            context.get('today', timezone.now())
        ).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        listing = instance.getEvents(
            dateTime=today_start,
            initial=context.get('allEvents', Event.objects.none())
        )

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
