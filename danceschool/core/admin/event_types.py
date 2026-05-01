from django.contrib import admin
from django.forms import ModelForm, SplitDateTimeField, HiddenInput, ChoiceField
from django.utils.translation import gettext_lazy as _

from cms.admin.placeholderadmin import FrontendEditableAdminMixin
from django_admin_listfilter_dropdown.filters import ChoiceDropdownFilter, RelatedDropdownFilter
from adminsortable2.admin import SortableAdminMixin

from ..models import Series, PublicEvent, Event, Location, PricingTier
from ..constants import getConstant
from ..forms.inputs import LocationWithDataWidget
from ..mixins import ModelTemplateMixin

from .event_base import WIDGET_FORMATS, EventChildAdmin
from .event_roles import EventRoleInline
from .event_occurrences import EventOccurrenceInline
from .event_addons import EventAddOnInline
from .staff import EventStaffMemberInline


class SeriesAdminForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Series have registration enabled by default
        self.fields['status'].initial = Event.RegStatus.enabled

        # Make registrationOpenDate a split date/time field.
        self.fields['registrationOpenDate'] = SplitDateTimeField(
            label=_('Optional opening date/time for registrations'),
            input_time_formats=WIDGET_FORMATS,
            required=False
        )

        # Locations are required for Series even though they are not for all events.
        self.fields['location'].required = True

        # Allow adding additional rooms from a popup on Location, but not a popup on Room
        self.fields['room'].widget.can_add_related = False
        self.fields['room'].widget.can_change_related = False

        # Impose restrictions on new records, but not on existing ones.
        if not kwargs.get('instance', None):
            # Filter out former locations for new records
            self.fields['location'].queryset = Location.objects.exclude(
                status=Location.StatusChoices.former
            )

            # Filter out Pricing Tiers that are expired (i.e. no longer in use)
            self.fields['pricingTier'].queryset = PricingTier.objects.filter(expired=False)

            # Set initial values for capacity here because they will automatically
            # update if the constant is changed.  Through Javascript, this
            # should also change when the Location is changed.
            self.fields['capacity'].initial = getConstant(name='registration__defaultEventCapacity')

    # Use the custom location capacity widget to ensure that Javascript can update
    # location specific capacities.
    class Meta:
        model = Series
        exclude = []
        widgets = {
            'location': LocationWithDataWidget,
        }

    class Media:
        js = (
            'admin/js/vendor/jquery/jquery.min.js',
            'https://cdn.jsdelivr.net/npm/bootstrap-datepicker@1.10.1/dist/js/bootstrap-datepicker.min.js',
            'https://cdn.jsdelivr.net/gh/jonthornton/jquery-timepicker@1.14.1/jquery.timepicker.js',
            'admin/js/jquery.init.js',
            'js/serieslocation_capacity_change.js',
            'js/location_related_objects_lookup.js',
        )
        css = {
            'all': (
                'https://cdn.jsdelivr.net/gh/jonthornton/jquery-timepicker@1.14.1/jquery.timepicker.min.css',
                'https://cdn.jsdelivr.net/npm/bootstrap-datepicker@1.10.1/dist/css/bootstrap-datepicker.standalone.min.css'
            )
        }


@admin.register(Series)
class SeriesAdmin(FrontendEditableAdminMixin, EventChildAdmin):
    base_model = Series
    form = SeriesAdminForm
    show_in_index = True

    uuid_link_view_name = 'classViewUUID'

    inlines = [
        EventRoleInline, EventOccurrenceInline, EventStaffMemberInline
    ]
    list_display = (
        'name', 'series_month', 'location', 'class_time', 'status',
        'registrationOpen', 'pricingTier', 'category', 'session', 'customers'
    )
    list_editable = ('status', 'category', 'session')
    list_filter = (
        ('location', RelatedDropdownFilter),
        ('status', ChoiceDropdownFilter),
        'registrationOpen',
        ('category', RelatedDropdownFilter),
        ('session', RelatedDropdownFilter),
        ('pricingTier', RelatedDropdownFilter),
    )
    search_fields = ('classDescription__title',)
    autocomplete_fields = ['classDescription', ]

    def customers(self, obj):
        return obj.numRegistered
    customers.short_description = _('# Registered Students')

    def series_month(self, obj):
        from calendar import month_name
        return '%s %s' % (month_name[obj.month or 0], obj.year or '')

    def class_time(self, obj):
        if obj.startTime:
            return obj.startTime.strftime('%A, %I:%M %p')

    fieldsets = (
        (None, {
            'fields': (
                'classDescription', ('location', 'room'), 'pricingTier',
                ('category', 'session'), ('partnerRequired', 'allowDropins',),
                ('uuidLink', )
            ),
        }),
        (_('Override Display/Registration/Capacity'), {
            'classes': ('collapse', ),
            'fields': (
                ('status', 'calendarEvent'), 'registrationOpenDate',
                'closeAfterDays', 'capacity',
            ),
        }),
        (_('Additional data'), {
            'classes': ('collapse', ),
            'fields': ('data', ),
        }),
    )

    # This allows us to save the obj reference in order to process related
    # objects in an inline (staff substitutions)
    def get_form(self, request, obj=None, **kwargs):
        # just save obj reference for future processing in Inline
        request._obj_ = obj
        form = super().get_form(request, obj, **kwargs)
        form.admin_site = self.admin_site
        return form

    def save_model(self, request, obj, form, change):
        obj.submissionUser = request.user
        obj.save()


class PublicEventAdminForm(ModelTemplateMixin, ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['status'].initial = Event.RegStatus.disabled

        # Make registrationOpenDate a split date/time field.
        self.fields['registrationOpenDate'] = SplitDateTimeField(
            label=_('Optional opening date/time for registrations'),
            input_time_formats=WIDGET_FORMATS,
            required=False
        )

        # Allow adding additional rooms from a popup on Location, but not a popup on Room
        self.fields['room'].widget.can_add_related = False
        self.fields['room'].widget.can_change_related = False

        # Allow the user to choose from the registered template choices.
        self.fields['template'] = ChoiceField(
            choices=self.get_template_choices(self.Meta.model), required=True,
            initial=getConstant('general__defaultPublicEventPageTemplate')
        )

        # Impose restrictions on new records, but not on existing ones.
        if not kwargs.get('instance', None):
            # Filter out former locations
            self.fields['location'].queryset = Location.objects.exclude(
                status=Location.StatusChoices.former
            )

            # Filter out Pricing Tiers that are expired (i.e. no longer in use)
            self.fields['pricingTier'].queryset = PricingTier.objects.filter(expired=False)

            # Set initial values for capacity here because they will automatically update if the
            # constant is changed
            self.fields['capacity'].initial = getConstant(name='registration__defaultEventCapacity')

    # Use the custom location capacity widget to ensure that Javascript can
    # update location specific capacities.
    class Meta:
        model = PublicEvent
        exclude = [
            'month', 'year', 'startTime', 'endTime', 'duration', 'submissionUser',
            'registrationOpen'
        ]
        widgets = {
            'location': LocationWithDataWidget,
            'submissionUser': HiddenInput(),
        }

    class Media:
        js = (
            'admin/js/vendor/jquery/jquery.min.js',
            'https://cdn.jsdelivr.net/npm/bootstrap-datepicker@1.10.1/dist/js/bootstrap-datepicker.min.js',
            'https://cdn.jsdelivr.net/gh/jonthornton/jquery-timepicker@1.14.1/jquery.timepicker.js',
            'admin/js/jquery.init.js',
            'js/location_related_objects_lookup.js',
        )
        css = {
            'all': (
                'https://cdn.jsdelivr.net/gh/jonthornton/jquery-timepicker@1.14.1/jquery.timepicker.min.css',
                'https://cdn.jsdelivr.net/npm/bootstrap-datepicker@1.10.1/dist/css/bootstrap-datepicker.standalone.min.css'
            )
        }


@admin.register(PublicEvent)
class PublicEventAdmin(
    SortableAdminMixin, FrontendEditableAdminMixin, EventChildAdmin
):
    base_model = PublicEvent
    form = PublicEventAdminForm
    show_in_index = True

    uuid_link_view_name = 'eventViewUUID'

    list_display = (
        'name', 'numOccurrences', 'firstOccurrenceTime', 'lastOccurrenceTime',
        'location', 'status', 'registrationOpen', 'pricingTier', 'category',
        'session', 'numRegistered'
    )
    list_filter = (
        ('location', RelatedDropdownFilter),
        ('status', ChoiceDropdownFilter),
        'registrationOpen',
        ('pricingTier', RelatedDropdownFilter),
        ('category', RelatedDropdownFilter),
        ('session', RelatedDropdownFilter),
    )
    list_editable = ('status', 'category', 'session')
    search_fields = ('name', )
    ordering = ('-endTime', )
    prepopulated_fields = {'slug': ('title', )}
    inlines = [
        EventRoleInline, EventOccurrenceInline, EventStaffMemberInline,
        EventAddOnInline
    ]

    fieldsets = (
        (None, {
            'fields': (
                'title', 'slug', 'category', 'session', 'partnerRequired',
                ('location', 'room'),
            )
        }),
        (_('Registration/Visibility'), {
            'fields': (
                ('status', 'calendarEvent'),
                ('registrationOpenDate', 'closeAfterDays'),
                ('pricingTier', 'capacity'),
            ),
        }),
        (_('Description/Link'), {
            'fields': (
                'descriptionField', 'shortDescriptionField', 'template',
                'link', 'uuidLink',
            )
        }),
        (_('Additional data'), {
            'classes': ('collapse', ),
            'fields': ('data', ),
        }),
    )

    # This allows us to save the obj reference in order to process related
    # objects in an inline (staff substitutions)
    def get_form(self, request, obj=None, **kwargs):
        # just save obj reference for future processing in Inline
        request._obj_ = obj
        return super().get_form(request, obj, **kwargs)

    def save_model(self, request, obj, form, change):
        obj.submissionUser = request.user
        obj.save()
