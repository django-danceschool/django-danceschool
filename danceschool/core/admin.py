from django.contrib import admin
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.forms import (
    ModelForm, SplitDateTimeField, HiddenInput, RadioSelect,
    ModelMultipleChoiceField, ModelChoiceField, ChoiceField
)
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils.translation import gettext, gettext_lazy as _
from django.template.response import SimpleTemplateResponse
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseRedirect

from calendar import month_name
from polymorphic.admin import (
    PolymorphicParentModelAdmin, PolymorphicChildModelAdmin,
    PolymorphicChildModelFilter
)
from cms.admin.placeholderadmin import FrontendEditableAdminMixin
import json
import six
from dal import autocomplete

from .models import (
    EventSession, Event, PublicEventCategory, Series, SeriesCategory,
    PublicEvent, EventOccurrence, SeriesTeacher, StaffMember, Instructor,
    SubstituteTeacher, Registration, EventRegistration, ClassDescription,
    CustomerGroup, Customer, Location, PricingTier, DanceRole, DanceType,
    DanceTypeLevel, EmailTemplate, EventStaffMember, SeriesStaffMember,
    EventStaffCategory, EventRole, Invoice, InvoiceItem, Room
)
from .constants import getConstant
from .forms import LocationWithDataWidget
from .mixins import ModelTemplateMixin


######################################
# Admin action for repeating events


def repeat_events(modeladmin, request, queryset):
    selected = request.POST.getlist(ACTION_CHECKBOX_NAME)
    ct = ContentType.objects.get_for_model(queryset.model)
    return HttpResponseRedirect(reverse('repeatEvents') + "?ct=%s&ids=%s" % (ct.pk, ", ".join(selected)))


repeat_events.short_description = _('Duplicate selected events')


######################################
# Inline classes


class EventRoleInline(admin.TabularInline):
    model = EventRole
    extra = 1
    classes = ['collapse']

    verbose_name = _('Event-specific dance role')
    verbose_name_plural = _('Event-specific dance roles (override default)')


class EventStaffMemberInlineForm(ModelForm):

    staffMember = ModelChoiceField(
        queryset=StaffMember.objects.all(),
        widget=autocomplete.ModelSelect2(
            url='autocompleteStaffMember',
            attrs={
                # This will set the input placeholder attribute:
                'data-placeholder': _('Enter a staff member name'),
                # This will set the yourlabs.Autocomplete.minimumCharacters
                # options, the naming conversion is handled by jQuery
                'data-minimum-input-length': 1,
                'data-max-results': 10,
                'class': 'modern-style',
            },
        )
    )

    class Media:
        js = (
            'admin/js/vendor/jquery/jquery.min.js',
            'admin/js/jquery.init.js',
        )


class SeriesTeacherInlineForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['staffMember'].label = _('Instructor')
        self.fields['category'].initial = getConstant('general__eventStaffCategoryInstructor').id

        # Impose restrictions on new records, but not on existing ones.
        if not kwargs.get('instance', None):
            # Filter out retired teachers
            self.fields['staffMember'].queryset = StaffMember.objects.filter(
                instructor__isnull=False,
            ).exclude(
                instructor__status__in=[
                    Instructor.InstructorStatus.retired,
                    Instructor.InstructorStatus.hidden,
                    Instructor.InstructorStatus.retiredGuest
                ]
            )
        else:
            self.fields['staffMember'].queryset = StaffMember.objects.all()

        self.fields['staffMember'].queryset = self.fields['staffMember'].queryset.order_by(
            'instructor__status', 'firstName', 'lastName'
        )

    class Meta:
        widgets = {
            'category': HiddenInput(),
        }


class SeriesTeacherInline(admin.StackedInline):
    model = SeriesTeacher
    form = SeriesTeacherInlineForm
    exclude = ('replacedStaffMember', 'occurrences', 'submissionUser')
    extra = 1

    def save_model(self, request, obj, form, change):
        obj.replacedStaffMember = None
        obj.occurrences = obj.event.eventoccurrence_set.all()
        obj.submissionUser = request.user
        obj.save()


class SubstituteTeacherInlineForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['staffMember'].label = _('Instructor')
        self.fields['replacedStaffMember'].required = True
        self.fields['category'].initial = getConstant('general__eventStaffCategorySubstitute').id

        # Impose restrictions on new records, but not on existing ones.
        if not kwargs.get('instance', None):
            # Filter out retired teachers
            self.fields['staffMember'].queryset = StaffMember.objects.exclude(
                instructor__status__in=[
                    Instructor.InstructorStatus.retired,
                    Instructor.InstructorStatus.hidden
                ]
            )
        else:
            self.fields['staffMember'].queryset = StaffMember.objects.all()

        self.fields['staffMember'].queryset = self.fields['staffMember'].queryset.order_by(
            'instructor__status', 'firstName', 'lastName'
        )

    class Meta:
        widgets = {
            'category': HiddenInput(),
        }


class SubstituteTeacherInline(admin.StackedInline):
    model = SubstituteTeacher
    form = SubstituteTeacherInlineForm
    exclude = ('submissionUser', )
    extra = 0

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name == 'replacedStaffMember':
            if request._obj_ is not None:
                # set the query set to whatever you like
                field.queryset = SeriesTeacher.objects.filter(event=request._obj_)
            else:
                field.queryset = field.queryset.none()
        return field

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name == 'occurrences':
            if request._obj_ is not None:
                # set the query set to whatever you like
                field.queryset = EventOccurrence.objects.filter(event=request._obj_)
            else:
                field.queryset = field.queryset.none()
        return field

    def save_model(self, request, obj, form, change):
        obj.submissionUser = request.user
        obj.save()


class EventStaffMemberInline(admin.TabularInline):
    model = EventStaffMember
    exclude = ('submissionUser', 'replacedStaffMember')
    fields = ('staffMember', 'category', 'specifiedHours', 'occurrences')
    extra = 0
    form = EventStaffMemberInlineForm

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name == 'occurrences':
            if request._obj_ is not None:
                # set the query set to whatever you like
                field.queryset = EventOccurrence.objects.filter(event=request._obj_)
            else:
                field.queryset = field.queryset.none()
        return field

    def save_model(self, request, obj, form, change):
        obj.submissionUser = request.user
        obj.save()


class SeriesStaffMemberInline(EventStaffMemberInline):
    ''' Use the proxy model to exclude SeriesTeachers and SubstituteTeachers. '''
    model = SeriesStaffMember


class EventRegistrationInline(admin.StackedInline):
    model = EventRegistration
    extra = 0
    fields = [
        'event', 'role', 'cancelled', 'dropIn', 'occurrences',
        'item_grossTotal', 'item_total'
    ]
    add_readonly_fields = ['item_grossTotal', 'item_total',]
    readonly_fields = ['event', 'item_grossTotal', 'item_total', 'dropIn', 'occurrences']

    def has_add_permission(self, request, obj=None):
        '''
        EventRegistrations can only be added to Registrations that are not final.
        '''
        if obj and obj.final:
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        '''
        EventRegistrations can only be deleted from Registrations that are not
        final.
        '''
        if obj and obj.final:
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        if not obj:
            return self.add_readonly_fields
        return self.readonly_fields

    def item_grossTotal(self, obj):
        return getattr(obj.invoiceItem, 'grossTotal', None)
    item_grossTotal.short_description = _('Total before discounts')

    def item_total(self, obj):
        return getattr(obj.invoiceItem, 'total', None)
    item_total.short_description = _('Total billed amount')


class EventOccurrenceInlineForm(ModelForm):
    WIDGET_FORMATS = ['%I:%M%p', '%I:%M %p', '%I:%M', '%H:%M:%S', '%H:%M']

    startTime = SplitDateTimeField(required=True, label=_('Start Date/Time'), input_time_formats=WIDGET_FORMATS)
    endTime = SplitDateTimeField(required=True, label=_('End Date/Time'), input_time_formats=WIDGET_FORMATS)


class EventOccurrenceInline(admin.TabularInline):
    model = EventOccurrence
    form = EventOccurrenceInlineForm
    extra = 1

    class Media:
        js = (
            'moment/moment.min.js',
            'bootstrap-datepicker/js/bootstrap-datepicker.min.js',
            'timepicker/jquery.timepicker.min.js',
            'datepair/datepair.min.js',
            'datepair/jquery.datepair.min.js',
            'js/eventadmin_pickers.js'
        )
        css = {
            'all': ('timepicker/jquery.timepicker.css', 'bootstrap-datepicker/css/bootstrap-datepicker.standalone.min.css')
        }


######################################
# Registration related admin classes


class InvoiceAdminForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Invoices that are already in a finalized type of status cannot be
        # changed to a non-finalized type of status.  This is enforced at the
        # model level; this code just limits the dropdown choices.
        instance = kwargs.get('instance', None)

        if getattr(instance, 'status', None) in [
            Invoice.PaymentStatus.paid, Invoice.PaymentStatus.needsCollection,
            Invoice.PaymentStatus.fullRefund,
        ]:
            limited_choices = [
                x for x in Invoice.PaymentStatus.choices if x[0] in [
                    Invoice.PaymentStatus.paid,
                    Invoice.PaymentStatus.needsCollection,
                    Invoice.PaymentStatus.fullRefund
                ]
            ]
            self.fields['status'] = ChoiceField(
                choices=limited_choices, required=True,
            )

    class Meta:
        model = Invoice
        exclude = []


class InvoiceItemInline(admin.StackedInline):
    model = InvoiceItem
    extra = 0
    add_fields = [('description', 'grossTotal', 'total', 'taxRate', 'taxes', 'fees', 'adjustments'), ]
    fields = ['id', ('description', 'grossTotal', 'total', 'taxRate', 'taxes', 'fees', 'adjustments'), ]
    add_readonly_fields = ['fees', ]
    readonly_fields = ['id', 'grossTotal', 'total', 'taxRate', 'taxes', 'fees']

    def has_add_permission(self, request, obj=None):
        '''
        InvoiceItems can only be added when an invoice's status is preliminary
        or unpaid.
        '''
        if obj and not obj.itemsEditable:
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        '''
        InvoiceItems can only be deleted when an invoice's status is preliminary
        or unpaid.
        '''
        if obj and not obj.itemsEditable:
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        if not obj or getattr(obj, 'itemsEditable', False):
            return self.add_readonly_fields
        return self.readonly_fields

    def get_fields(self, request, obj=None):
        if not obj or getattr(obj, 'itemsEditable', False):
            return self.add_fields
        return super().get_fields(request, obj)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    form = InvoiceAdminForm
    inlines = [InvoiceItemInline, ]
    list_display = [
        'id', 'recipientInfo', 'status', 'outstandingBalance',
        'modifiedDate', 'links'
    ]
    list_filter = ['status', 'paidOnline', 'creationDate', 'modifiedDate']
    search_fields = ['id', 'comments']
    ordering = ['-modifiedDate', ]
    readonly_fields = [
        'id', 'recipientInfo', 'total', 'adjustments', 'taxes', 'fees',
        'netRevenue', 'outstandingBalance', 'creationDate', 'modifiedDate',
        'links', 'submissionUser', 'collectedByUser'
    ]
    view_on_site = True

    fieldsets = (
        (None, {
            'fields': (
                'id', ('firstName', 'lastName', 'email'), 'comments', 'status',
                'amountPaid', 'outstandingBalance', 'links'
            ),
        }),
        (_('Financial Details'), {
            'classes': ('collapse', ),
            'fields': ('total', 'adjustments', 'taxes', 'fees', 'netRevenue'),
        }),
        (_('Dates'), {
            'classes': ('collapse', ),
            'fields': ('creationDate', 'modifiedDate'),
        }),
        (_('Additional data'), {
            'classes': ('collapse', ),
            'fields': ('submissionUser', 'collectedByUser', 'data'),
        }),
    )

    add_fieldsets = (
        (None, {
            'fields': (
                ('firstName', 'lastName', 'email'), 'comments', 'status',
                'amountPaid',
            ),
        }),
        (_('Additional data'), {
            'classes': ('collapse', ),
            'fields': ('data', ),
        }),
    )

    def emailNotification(self, request, queryset):
        # Allows use of the email view to contact specific customers.
        selected = request.POST.getlist(ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect(
            reverse('sendInvoiceNotifications') +
            "?invoices=%s" % (", ".join(selected))
        )
    emailNotification.short_description = _('Send email notifications for selected invoices')

    actions = ['emailNotification', ]

    def recipientInfo(self, obj):
        if obj.firstName and obj.lastName and obj.email:
            return '%s %s: %s' % (obj.firstName, obj.lastName, obj.email)
        elif obj.email:
            return obj.email
    recipientInfo.short_description = _('Recipient')

    def viewInvoiceLink(self, obj):
        if obj.id:
            change_url = reverse('viewInvoice', args=(obj.id, ))
            return mark_safe(
                '<a href="%s">%s</a>' % (change_url, gettext('View'))
            )
    viewInvoiceLink.allow_tags = True
    viewInvoiceLink.short_description = _('Invoice')

    def notificationLink(self, obj):
        if obj.id:
            change_url = reverse('sendInvoiceNotifications', args=(obj.id, ))
            return mark_safe(
                '<a href="%s">%s</a>' % (change_url, gettext('Notify'))
            )
    notificationLink.allow_tags = True
    notificationLink.short_description = _('Invoice notification')

    def registrationLink(self, obj):
        if getattr(obj, 'registration', None):
            change_url = reverse('admin:core_registration_change', args=(obj.registration.id, ))
            return mark_safe(
                '<a href="%s">%s</a>' % (change_url, gettext('Registration'))
            )
    registrationLink.allow_tags = True
    registrationLink.short_description = _('Registration')

    def refundLink(self, obj):
        change_url = reverse('refundProcessing', args=(obj.id, ))
        return mark_safe(
            '<a href="%s">%s</a>' % (change_url, gettext('Refund'))
        )
    refundLink.allow_tags = True
    refundLink.short_description = _('Refund')

    def links(self, obj):
        button_start = ''
        button_end = ''

        return mark_safe(
            button_start + '<br />'.join([
                self.viewInvoiceLink(obj) or '',
                self.notificationLink(obj) or '',
                self.refundLink(obj) or '',
                self.registrationLink(obj) or '',
            ]) + button_end
        )
    links.allow_tags = True
    links.short_description = _('Links')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.submissionUser = request.user
        super().save_model(request, obj, form, change)

    def get_fieldsets(self, request, obj=None):
        if not obj:
            return self.add_fieldsets
        else:
            return super().get_fieldsets(request, obj)


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    inlines = [EventRegistrationInline]
    list_display = ['final', 'customer', 'dateTime', 'total', 'student']
    list_filter = ['final', 'dateTime', 'student', 'invoice__paidOnline']
    search_fields = [
        '=customer__first_name', '=customer__last_name',
        'customer__email', 'email', 'phone'
    ]
    ordering = ('-final', '-dateTime', )
    fields = (
        ('final', 'invoice_expiry'), 'email', 'phone', 'customer_link', 'invoice_link',
        'total', 'student', 'dateTime', 'comments',
        'howHeardAboutUs', 'submissionUser',
    )
    readonly_fields = ('total', 'customer_link', 'invoice_link', 'invoice_expiry')

    def customer_link(self, obj):
        change_url = reverse('admin:core_customer_change', args=(obj.customer.id, ))
        return mark_safe('<a href="%s">%s</a>' % (change_url, obj.customer))
    customer_link.allow_tags = True
    customer_link.short_description = _("Customer")

    def invoice_link(self, obj):
        change_url = reverse('admin:core_invoice_change', args=(obj.invoice.id, ))
        return mark_safe('<a href="%s">%s</a>' % (change_url, obj.invoice))
    invoice_link.allow_tags = True
    invoice_link.short_description = _("Invoice")

    def invoice_expiry(self, obj):
        return obj.invoice.expirationDate
    invoice_expiry.short_description = _("Expiration Date")

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            if not hasattr(instance, 'customer'):
                instance.customer = instance.registration.customer
            instance.save()
        formset.save_m2m()


######################################
# Miscellaneous Admin classes

class ClassDescriptionAdminForm(ModelTemplateMixin, ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Allow the user to choose from the registered template choices.
        self.fields['template'] = ChoiceField(
            choices=self.get_template_choices(Series), required=True,
            initial=getConstant('general__defaultSeriesPageTemplate')
        )

    class Meta:
        model = ClassDescription
        exclude = []



@admin.register(ClassDescription)
class ClassDescriptionAdmin(FrontendEditableAdminMixin, admin.ModelAdmin):
    list_display = ['title', 'danceTypeLevel', ]
    list_filter = ('danceTypeLevel', )
    search_fields = ('title', )
    prepopulated_fields = {"slug": ("title", )}
    form = ClassDescriptionAdminForm


class CustomerRegistrationInline(admin.StackedInline):
    model = Registration
    fields = ('registration_link', 'eventregistration_list')
    readonly_fields = ('registration_link', 'eventregistration_list')
    extra = 0

    def registration_link(self, obj):
        change_url = reverse('admin:core_registration_change', args=(obj.id, ))
        if obj.dateTime:
            return mark_safe(
                '%s: <a href="%s">%s</a>' % (
                    obj.dateTime.strftime('%b. %d, %Y'), change_url, obj.__str__()
                )
            )
        else:
            return mark_safe('<a href="%s">%s</a>' % (change_url, obj.__str__()))

    registration_link.short_description = _('Registration')
    registration_link.allow_tags = True

    def eventregistration_list(self, obj):
        eregs = obj.eventregistration_set.all()
        if not eregs:
            return ''
        return_string = '<ul>'

        for ereg in eregs:
            this_string = '<li>'
            if ereg.cancelled:
                this_string += '<em>%s</em> ' % _('CANCELLED:')
            if ereg.dropIn:
                this_string += '<em>%s</em> ' % _('DROP-IN:')
            if ereg.event.month:
                this_string += '%s %s, %s</li>' % (
                    month_name[ereg.event.month], ereg.event.year, ereg.event.name
                )
            else:
                this_string += '%s</li>' % ereg.event.name
            return_string += this_string
        return return_string
    eventregistration_list.short_description = _('Event Registrations')
    eventregistration_list.allow_tags = True

    def has_add_permission(self, request, obj=None):
        '''
        Prevents adding new registrations without going through
        the standard registration process.
        '''
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        ''' Only show finalized registrations. '''
        qs = super().get_queryset(request)
        return qs.filter(final=False)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('fullName', 'numClassSeries', 'numPublicEvents')
    search_fields = ('=first_name', '=last_name', 'email')
    readonly_fields = ('data', 'numClassSeries', 'numPublicEvents')

    fieldsets = (
        (None, {
            'fields': (('first_name', 'last_name'), 'email', 'phone', 'user', )
        }),
        (_('Groups'), {
            'fields': ('groups', )
        }),
        (_('Additional Customer Data'), {
            'classes': ('collapse', ),
            'fields': (('numClassSeries', 'numPublicEvents', ), 'data', ),
        }),
    )

    def emailCustomers(self, request, queryset):
        # Allows use of the email view to contact specific customers.
        selected = request.POST.getlist(ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect(reverse('emailStudents') + "?customers=%s" % (
            ", ".join(selected)
        ))
    emailCustomers.short_description = _('Email selected customers')

    inlines = [CustomerRegistrationInline, ]
    actions = ['emailCustomers']


class CustomerGroupAdminForm(ModelForm):
    customers = ModelMultipleChoiceField(
        queryset=Customer.objects.all(),
        required=False,
        widget=autocomplete.ModelSelect2Multiple(
            url='autocompleteCustomer',
            attrs={
                # This will set the input placeholder attribute:
                'data-placeholder': _('Enter a customer name'),
                # This will set the yourlabs.Autocomplete.minimumCharacters
                # options, the naming conversion is handled by jQuery
                'data-minimum-input-length': 2,
                'data-max-results': 4,
                'class': 'modern-style',
            }
        )
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['customers'] = self.instance.customer_set.values_list('pk', flat=True)

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        if instance.pk:
            instance.customer_set.clear()
            instance.customer_set.add(*self.cleaned_data['customers'])
        return instance

    class Meta:
        model = CustomerGroup
        exclude = []

    class Media:
        js = (
            'admin/js/vendor/jquery/jquery.min.js',
            'admin/js/jquery.init.js',
        )


@admin.register(CustomerGroup)
class CustomerGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'memberCount')
    readonly_fields = ('memberCount', )
    form = CustomerGroupAdminForm

    def emailCustomers(self, request, queryset):
        # Allows use of the email view to contact specific customer groups.
        selected = request.POST.getlist(ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect(reverse('emailStudents') + "?customergroup=%s" % (", ".join(selected)))
    emailCustomers.short_description = _('Email selected customer groups')

    actions = ['emailCustomers']


@admin.register(EventSession)
class EventSessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'startTime', 'endTime')
    ordering = ('startTime', 'name')
    readonly_fields = ('startTime', 'endTime')
    list_filter = ('startTime', 'endTime')
    prepopulated_fields = {'slug': ('name', )}

    fields = ('name', 'description', 'slug', ('startTime', 'endTime'))


class RoomInline(admin.StackedInline):
    model = Room
    extra = 0
    fields = (('name', 'defaultCapacity'), 'description')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    inlines = []

    list_display = ('name', 'location', 'defaultCapacity')
    list_display_links = ('name', )
    list_editable = ('defaultCapacity', )
    list_filter = ('location', )

    ordering = ('location__name', 'name')

    fields = ('location', 'name', 'defaultCapacity', 'description')


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    inlines = [RoomInline, ]

    list_display = ('name', 'address', 'city', 'orderNum', 'status')
    list_display_links = ('name', )
    list_editable = ('orderNum', 'status')
    list_filter = ('status', 'city')

    ordering = ('status', 'orderNum')

    def response_add(self, request, obj, post_url_continue=None):
        '''
        This just modifies the normal ModelAdmin process in order to
        pass capacity and room options for the added Location along with
        the location's name and ID.
        '''

        IS_POPUP_VAR = '_popup'
        TO_FIELD_VAR = '_to_field'

        if IS_POPUP_VAR in request.POST:
            to_field = request.POST.get(TO_FIELD_VAR)
            if to_field:
                attr = str(to_field)
            else:
                attr = obj._meta.pk.attname
            value = obj.serializable_value(attr)
            popup_response_data = json.dumps({
                'value': six.text_type(value),
                'obj': six.text_type(obj),
                # Add this extra data
                'defaultCapacity': obj.defaultCapacity,
                'roomOptions': json.dumps([
                    {'id': x.id, 'name': x.name, 'defaultCapacity': x.defaultCapacity} for
                    x in obj.room_set.all()
                ]),
            })

            # Return a modified template
            return SimpleTemplateResponse('core/admin/location_popup_response.html', {
                'popup_response_data': popup_response_data,
            })

        # Otherwise just use the standard ModelAdmin method
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        '''
        This just modifies the normal ModelAdmin process in order to
        pass capacity and room options for the modified Location along with
        the location's name and ID.
        '''

        IS_POPUP_VAR = '_popup'
        TO_FIELD_VAR = '_to_field'

        if IS_POPUP_VAR in request.POST:
            to_field = request.POST.get(TO_FIELD_VAR)
            attr = str(to_field) if to_field else obj._meta.pk.attname
            # Retrieve the `object_id` from the resolved pattern arguments.
            value = request.resolver_match.args[0] if request.resolver_match.args else None
            new_value = obj.serializable_value(attr)
            popup_response_data = json.dumps({
                'action': 'change',
                'value': six.text_type(value),
                'obj': six.text_type(obj),
                'new_value': six.text_type(new_value),
                # Add this extra data
                'defaultCapacity': obj.defaultCapacity,
                'roomOptions': json.dumps([
                    {'id': x.id, 'name': x.name, 'defaultCapacity': x.defaultCapacity} for
                    x in obj.room_set.all()
                ]),
            })

            # Return a modified template
            return SimpleTemplateResponse('core/admin/location_popup_response.html', {
                'popup_response_data': popup_response_data,
            })
        return super().response_change(request, obj)


@admin.register(PricingTier)
class PricingTierAdmin(admin.ModelAdmin):
    list_display = ('name', 'expired')
    list_filter = ('expired', )

    # Need to specify an empty list of inlines so that discounts app can
    # add to the list if it is enabled.
    inlines = []


class EmailTemplateAdminForm(ModelForm):

    class Meta:
        model = EmailTemplate
        exclude = []

        widgets = {
            'richTextChoice': RadioSelect,
        }

    class Media:
        js = ('js/emailtemplate_contenttype.js', )


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    form = EmailTemplateAdminForm

    list_display = ('name', 'richTextChoice', 'hideFromForm')
    list_filter = ('richTextChoice', 'groupRequired', 'hideFromForm')
    ordering = ('name', )

    fieldsets = (
        (None, {
            'fields': ('name', 'richTextChoice', 'subject', ),
        }),
        (_('Plain text content'), {
            'fields': ('content', ),
        }),
        (_('Rich text HTML content'), {
            'fields': ('html_content', ),
        }),
        (None, {
            'fields': (
                'defaultFromName', 'defaultFromAddress', 'defaultCC',
                'groupRequired', 'hideFromForm'
            ),
        }),
    )


######################################
# Staff and subclass admins
class InstructorInline(admin.StackedInline):
    model = Instructor
    exclude = []
    extra = 0
    max_num = 1
    template = 'core/admin/instructor_stackedinline.html'


@admin.register(StaffMember)
class StaffMemberAdmin(FrontendEditableAdminMixin, admin.ModelAdmin):
    list_display = (
        'fullName', 'privateEmail', 'categories_list', 'instructor_status',
        'instructor_availableForPrivates'
    )
    list_display_links = ('fullName', )
    list_editable = ('privateEmail', )
    list_filter = ('categories', 'instructor__status', 'instructor__availableForPrivates')
    search_fields = ('=firstName', '=lastName', 'publicEmail', 'privateEmail')
    ordering = ('lastName', 'firstName')
    inlines = [InstructorInline, ]

    # Allows overriding from other apps
    actions = []

    fieldsets = (
        (None, {
            'fields': ('firstName', 'lastName', 'userAccount', 'categories')
        }),
        (_('Contact'), {
            'fields': ('publicEmail', 'privateEmail', 'phone'),
        }),
        (_('Bio/Photo'), {
            'fields': ('image', 'bio'),
        }),
    )

    def instructor_status(self, obj):
        instructor = getattr(obj, 'instructor', None)
        if instructor:
            return instructor.get_status_display()
    instructor_status.short_description = _('Instructor status')

    def instructor_availableForPrivates(self, obj):
        return getattr(getattr(obj, 'instructor'), 'availableForPrivates')
    instructor_availableForPrivates.short_description = _('Available for private lessons')

    def categories_list(self, obj):
        return ', '.join([x.name for x in obj.categories.all()])
    categories_list.short_description = _('Staff categories')

    class Media:
        js = ('bootstrap/js/bootstrap.min.js', )
        css = {'all': ('bootstrap/css/bootstrap.min.css', )}


######################################
# Event and subclass admins


class EventChildAdmin(PolymorphicChildModelAdmin):
    '''
    Base admin class for all child models
    '''
    base_model = Event

    readonly_fields = ['uuidLink', ]

    actions = [repeat_events, ]

    def uuidLink(self, obj):
        address = reverse('singleClassRegistration', args=[obj.uuid, ])
        return mark_safe('<a href="%s">%s</a>' % (address, address))
    uuidLink.short_description = _('Direct Registration Link')
    uuidLink.allow_tags = True


class SeriesAdminForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Series have registration enabled by default
        self.fields['status'].initial = Event.RegStatus.enabled

        # Locations are required for Series even though they are not for all events.
        self.fields['location'].required = True

        # Allow adding additional rooms from a popup on Location, but not a popup on Room
        self.fields['room'].widget.can_add_related = False
        self.fields['room'].widget.can_change_related = False

        self.fields['classDescription'] = ModelChoiceField(
            queryset=ClassDescription.objects.all(),
            widget=RelatedFieldWidgetWrapper(
                autocomplete.ModelSelect2(
                    url='autocompleteClassDescription',
                    attrs={
                        # This will set the input placeholder attribute:
                        'data-placeholder': _('Enter an existing class series title or description'),
                        # This will set the yourlabs.Autocomplete.minimumCharacters
                        # options, the naming conversion is handled by jQuery
                        'data-minimum-input-length': 2,
                        'data-max-results': 10,
                        'class': 'modern-style',
                    },
                ),
                rel=Series._meta.get_field('classDescription').remote_field,
                admin_site=self.admin_site,
                can_add_related=True,
                can_change_related=True,
            )
        )

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
            'classDescription': autocomplete.ModelSelect2(
                url='autocompleteClassDescription',
                attrs={
                    # This will set the input placeholder attribute:
                    'data-placeholder': _('Enter a series title'),
                    # This will set the yourlabs.Autocomplete.minimumCharacters
                    # options, the naming conversion is handled by jQuery
                    'data-minimum-input-length': 2,
                    'data-max-results': 10,
                    'class': 'modern-style',
                }
            ),
        }

    class Media:
        js = (
            'admin/js/vendor/jquery/jquery.min.js',
            'admin/js/jquery.init.js',
            'js/serieslocation_capacity_change.js',
            'js/location_related_objects_lookup.js',
        )


@admin.register(Series)
class SeriesAdmin(FrontendEditableAdminMixin, EventChildAdmin):
    base_model = Series
    form = SeriesAdminForm
    show_in_index = True

    inlines = [
        EventRoleInline, EventOccurrenceInline, SeriesTeacherInline,
        SubstituteTeacherInline, SeriesStaffMemberInline
    ]
    list_display = (
        'name', 'series_month', 'location', 'class_time', 'status',
        'registrationOpen', 'pricingTier', 'category', 'session', 'customers'
    )
    list_editable = ('status', 'category', 'session')
    list_filter = (
        'location', 'status', 'registrationOpen', 'category',
        'session', 'pricingTier'
    )

    def customers(self, obj):
        return obj.numRegistered
    customers.short_description = _('# Registered Students')

    def series_month(self, obj):
        return '%s %s' % (month_name[obj.month or 0], obj.year or '')

    def class_time(self, obj):
        if obj.startTime:
            return obj.startTime.strftime('%A, %I:%M %p')

    fieldsets = (
        (None, {
            'fields': (
                'classDescription', ('location', 'room'), 'pricingTier',
                ('category', 'session', 'allowDropins'), ('uuidLink', )
            ),
        }),
        (_('Override Display/Registration/Capacity'), {
            'classes': ('collapse', ),
            'fields': ('status', 'closeAfterDays', 'capacity',),
        }),
        (_('Additional data'), {
            'classes': ('collapse', ),
            'fields': ('data', ),
        }),
    )

    # This allows us to save the obj reference in order to process related
    # objects in an inline (substitute teachers)
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
        js = ('js/location_related_objects_lookup.js', )


@admin.register(PublicEvent)
class PublicEventAdmin(FrontendEditableAdminMixin, EventChildAdmin):
    base_model = PublicEvent
    form = PublicEventAdminForm
    show_in_index = True

    list_display = (
        'name', 'numOccurrences', 'firstOccurrenceTime', 'lastOccurrenceTime',
        'location', 'status', 'registrationOpen', 'pricingTier', 'category',
        'session', 'numRegistered'
    )
    list_filter = (
        'location', 'status', 'registrationOpen',
        'pricingTier', 'category', 'session'
    )
    list_editable = ('status', 'category', 'session')
    search_fields = ('name', )
    ordering = ('-endTime', )
    prepopulated_fields = {'slug': ('title', )}
    inlines = [EventRoleInline, EventOccurrenceInline, EventStaffMemberInline]

    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'category', 'session', ('location', 'room'), )
        }),
        (_('Registration/Visibility'), {
            'fields': ('status', ('pricingTier', 'capacity'), ),
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
    # objects in an inline (substitute teachers)
    def get_form(self, request, obj=None, **kwargs):
        # just save obj reference for future processing in Inline
        request._obj_ = obj
        return super().get_form(request, obj, **kwargs)

    def save_model(self, request, obj, form, change):
        obj.submissionUser = request.user
        obj.save()


@admin.register(Event)
class EventParentAdmin(PolymorphicParentModelAdmin):
    '''
    The parent model admin for Events
    '''
    list_display = (
        'name', 'firstOccurrenceTime', 'lastOccurrenceTime', 'location',
        'status', 'registrationOpen'
    )

    base_model = Event
    child_models = (Series, PublicEvent)
    list_filter = (PolymorphicChildModelFilter, 'status', 'registrationOpen', 'location')
    list_editable = ('status', )
    polymorphic_list = True

    actions = [repeat_events, ]


@admin.register(PublicEventCategory)
class PublicEventCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'separateOnRegistrationPage', 'displayColor']
    prepopulated_fields = {'slug': ('name', )}


@admin.register(SeriesCategory)
class SeriesCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'separateOnRegistrationPage']
    prepopulated_fields = {'slug': ('name', )}


@admin.register(EventStaffCategory)
class EventStaffCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', ]

    # Allows financial app to add default wage inline
    inlines = []


# These admin classes are registered but need nothing additional
admin.site.register(DanceRole)
admin.site.register(DanceType)
admin.site.register(DanceTypeLevel)
