from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.middleware.csrf import get_token
from django.contrib.admin import TabularInline

from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool

from collections import OrderedDict
from adminsortable2.admin import SortableInlineAdminMixin

from .models import (
    RegisterEventPluginModel, RegisterEventPluginChoice,
    RegisterGuestSearchPluginModel,
    PublicRegisterNavPluginModel,
    PublicRegisterEventPluginModel, PublicRegisterEventPluginChoice,
)
from danceschool.core.models import Event, Series
from danceschool.core.mixins import PluginTemplateMixin
from danceschool.core.utils.timezone import ensure_localtime


class RegisterEventChoiceInline(SortableInlineAdminMixin, TabularInline):
    model = RegisterEventPluginChoice
    min_num = 1
    extra = 1
    fields = [
        'optionType', 'optionLabel', 'optionLocation',
        ('byRole', 'byPaymentMethod',),
        ('requireFullRegistration', 'registrationOpenDisplay', 'soldOutRule'),
        'voucherId', 'data'
    ]


class RegisterVoucherPlugin(CMSPluginBase):
    name = _('Register: Voucher Entry')
    cache = True
    module = _('Register')
    render_template = 'register/plugins/door_voucher.html'


class RegisterGuestSearchPlugin(CMSPluginBase):
    model = RegisterGuestSearchPluginModel
    name = _('Register: Customer/Guest Search')
    cache = True
    module = _('Register')
    render_template = 'register/plugins/door_guest_search.html'

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


class RegisterEventPlugin(PluginTemplateMixin, CMSPluginBase):
    model = RegisterEventPluginModel
    name = _('Register: Events at the door')
    cache = False
    module = _('Register')
    render_template = 'register/plugins/event_register.html'
    inlines = [RegisterEventChoiceInline, ]

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

            for choiceRule in instance.registereventpluginchoice_set.all():
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


class PublicRegisterNavPlugin(CMSPluginBase):
    model = PublicRegisterNavPluginModel
    name = _('Public Register: Navigation bar')
    module = _('Public Register')
    render_template = 'register/plugins/public_register_nav.html'
    cache = False


class PublicRegisterEventChoiceInline(SortableInlineAdminMixin, TabularInline):
    model = PublicRegisterEventPluginChoice
    min_num = 1
    extra = 1
    fields = ['optionLabel', 'soldOutRule', 'data']


class PublicRegisterEventPlugin(PluginTemplateMixin, CMSPluginBase):
    model = PublicRegisterEventPluginModel
    name = _('Public Register: Event listing')
    cache = False
    module = _('Public Register')
    render_template = 'register/plugins/public_event_register.html'
    inlines = [PublicRegisterEventChoiceInline]

    fieldsets = (
        (None, {
            'fields': ('title', 'eventType', 'registrationOpenLimit', 'occursWithinDays'),
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

        today_start = ensure_localtime(timezone.now()).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        listing = instance.getEvents(
            dateTime=today_start,
            initial=context.get('allEvents', Event.objects.none()),
        )

        request = context.get('request')
        user = getattr(request, 'user', None)
        can_dropin = user and user.has_perm('core.register_dropins')
        can_always_dropin = user and user.has_perm('core.override_register_dropins')

        now = timezone.now()

        register_choices = OrderedDict()
        for event in listing:
            choices = []
            for choice_rule in instance.publicregistereventpluginchoice_set.all():
                choices += choice_rule.addChoices(event)

            # Drop-in choices: one entry per upcoming occurrence, shown only to
            # users with drop-in registration permissions.
            dropin_choices = []
            if isinstance(event, Series) and (
                (can_dropin and getattr(event, 'allowDropins', False)) or
                can_always_dropin
            ):
                dropin_price = event.getBasePrice(dropIns=1)
                for occ in event.eventoccurrence_set.filter(endTime__gte=now).order_by('startTime'):
                    dropin_choices.append({
                        'occurrence': occ,
                        'price': dropin_price,
                        'choiceId': 'pubdropin_{}_{}'.format(event.id, occ.id),
                    })

            register_choices[event.id] = {
                'event': event,
                'choices': choices,
                'dropin_choices': dropin_choices,
            }

        context.update({
            'event_list': listing,
            'register_choices': register_choices,
        })
        return context


plugin_pool.register_plugin(RegisterVoucherPlugin)
plugin_pool.register_plugin(RegisterGuestSearchPlugin)
plugin_pool.register_plugin(RegisterEventPlugin)
plugin_pool.register_plugin(PublicRegisterEventPlugin)
plugin_pool.register_plugin(PublicRegisterNavPlugin)
