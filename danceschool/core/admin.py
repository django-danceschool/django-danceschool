from django.contrib import admin
from django.forms import ModelForm, SplitDateTimeField, HiddenInput, RadioSelect, ModelMultipleChoiceField
from django.utils.safestring import mark_safe
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from django.template.response import SimpleTemplateResponse
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseRedirect

from calendar import month_name
from polymorphic.admin import PolymorphicParentModelAdmin, PolymorphicChildModelAdmin, PolymorphicChildModelFilter
from cms.admin.placeholderadmin import FrontendEditableAdminMixin
import json
import six
from dal import autocomplete

from .models import EventSession, Event, PublicEventCategory, Series, SeriesCategory, PublicEvent, EventOccurrence, SeriesTeacher, StaffMember, Instructor, SubstituteTeacher, Registration, TemporaryRegistration, EventRegistration, TemporaryEventRegistration, ClassDescription, CustomerGroup, Customer, Location, PricingTier, DanceRole, DanceType, DanceTypeLevel, EmailTemplate, EventStaffMember, EventStaffCategory, EventRole, Invoice, InvoiceItem, Room
from .constants import getConstant
from .forms import LocationWithDataWidget


######################################
# Admin action for repeating events


def repeat_events(modeladmin, request, queryset):
    selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
    ct = ContentType.objects.get_for_model(queryset.model)
    return HttpResponseRedirect(reverse('repeatEvents') + "?ct=%s&ids=%s" % (ct.pk, ",".join(selected)))


repeat_events.short_description = _('Duplicate selected events')


######################################
# Inline classes


class EventRoleInline(admin.TabularInline):
    model = EventRole
    extra = 1
    classes = ['collapse']

    verbose_name = _('Event-specific dance role')
    verbose_name_plural = _('Event-specific dance roles (override default)')


class SeriesTeacherInlineForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super(SeriesTeacherInlineForm,self).__init__(*args,**kwargs)

        self.fields['staffMember'].label = _('Instructor')
        self.fields['category'].initial = getConstant('general__eventStaffCategoryInstructor').id

        # Impose restrictions on new records, but not on existing ones.
        if not kwargs.get('instance',None):
            # Filter out retired teachers
            self.fields['staffMember'].queryset = Instructor.objects.exclude(status__in=[Instructor.InstructorStatus.retired,Instructor.InstructorStatus.hidden,Instructor.InstructorStatus.retiredGuest])
        else:
            self.fields['staffMember'].queryset = Instructor.objects.all()

        self.fields['staffMember'].queryset = self.fields['staffMember'].queryset.order_by('status','firstName','lastName')

    class Meta:
        widgets = {
            'category': HiddenInput(),
        }


class SeriesTeacherInline(admin.StackedInline):
    model = SeriesTeacher
    form = SeriesTeacherInlineForm
    exclude = ('replacedStaffMember','occurrences','submissionUser')
    extra = 1

    def save_model(self,request,obj,form,change):
        obj.replacedStaffMember = None
        obj.occurrences = obj.event.eventoccurrence_set.all()
        obj.submissionUser = request.user
        obj.save()


class SubstituteTeacherInlineForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super(SubstituteTeacherInlineForm,self).__init__(*args,**kwargs)

        self.fields['staffMember'].label = _('Instructor')
        self.fields['replacedStaffMember'].required = True
        self.fields['category'].initial = getConstant('general__eventStaffCategorySubstitute').id

        # Impose restrictions on new records, but not on existing ones.
        if not kwargs.get('instance',None):
            # Filter out retired teachers
            self.fields['staffMember'].queryset = Instructor.objects.exclude(status__in=[Instructor.InstructorStatus.retired,Instructor.InstructorStatus.hidden])
        else:
            self.fields['staffMember'].queryset = Instructor.objects.all()

        self.fields['staffMember'].queryset = self.fields['staffMember'].queryset.order_by('status','firstName','lastName')

    class Meta:
        widgets = {
            'category': HiddenInput(),
        }


class SubstituteTeacherInline(admin.StackedInline):
    model = SubstituteTeacher
    form = SubstituteTeacherInlineForm
    exclude = ('submissionUser',)
    extra = 0

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        field = super(SubstituteTeacherInline, self).formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name == 'replacedStaffMember':
            if request._obj_ is not None:
                # set the query set to whatever you like
                field.queryset = SeriesTeacher.objects.filter(event=request._obj_)
            else:
                field.queryset = field.queryset.none()
        return field

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        field = super(SubstituteTeacherInline, self).formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name == 'occurrences':
            if request._obj_ is not None:
                # set the query set to whatever you like
                field.queryset = EventOccurrence.objects.filter(event=request._obj_)
            else:
                field.queryset = field.queryset.none()
        return field

    def save_model(self,request,obj,form,change):
        obj.submissionUser = request.user
        obj.save()


class EventStaffMemberInline(admin.StackedInline):
    model = EventStaffMember
    exclude = ('submissionUser','replacedStaffMember')
    extra = 0

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        field = super(EventStaffMemberInline, self).formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name == 'occurrences':
            if request._obj_ is not None:
                # set the query set to whatever you like
                field.queryset = EventOccurrence.objects.filter(event=request._obj_)
            else:
                field.queryset = field.queryset.none()
        return field

    def save_model(self,request,obj,form,change):
        obj.submissionUser = request.user
        obj.save()


class EventRegistrationInline(admin.StackedInline):
    model = EventRegistration
    extra = 0
    fields = ['event','role',('checkedIn','cancelled'),'dropIn','price','netPrice']
    readonly_fields = ['event','price','netPrice','dropIn']

    # These ensure that registration changes happen through the regular registration
    # process.
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class EventOccurrenceInlineForm(ModelForm):
    WIDGET_FORMATS = ['%I:%M%p','%I:%M %p','%I:%M','%H:%M:%S','%H:%M']

    startTime = SplitDateTimeField(required=True,label=_('Start Date/Time'),input_time_formats=WIDGET_FORMATS)
    endTime = SplitDateTimeField(required=True,label=_('End Date/Time'),input_time_formats=WIDGET_FORMATS)


class EventOccurrenceInline(admin.TabularInline):
    model = EventOccurrence
    form = EventOccurrenceInlineForm
    extra = 1

    class Media:
        js = ('timepicker/jquery.timepicker.min.js','jquery-ui/jquery-ui.min.js','datepair/datepair.min.js','moment/moment.min.js','datepair/jquery.datepair.min.js','js/eventadmin_pickers.js')
        css = {'all':('timepicker/jquery.timepicker.css','jquery-ui/jquery-ui.min.css',)}


######################################
# Registration related admin classes


class InvoiceItemInline(admin.StackedInline):
    model = InvoiceItem
    extra = 0
    add_fields = [('description','grossTotal','total','taxes','fees','adjustments'),]
    fields = ['id',('description','grossTotal','total','taxes','fees','adjustments'),]
    add_readonly_fields = ['fees',]
    readonly_fields = ['id','grossTotal','total','taxes','fees']

    # This ensures that InvoiceItems are not deleted except through
    # the regular registration process.  Invoice items can still be
    # manually added.
    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        if not obj:
            return self.add_readonly_fields
        return self.readonly_fields

    def get_fields(self, request, obj=None):
        if not obj:
            return self.add_fields
        return super(InvoiceItemInline, self).get_fields(request, obj)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    inlines = [InvoiceItemInline,]
    list_display = ['id','recipientInfo','status', 'total','netRevenue','outstandingBalance','creationDate','modifiedDate','links']
    list_filter = ['status', 'paidOnline', 'creationDate', 'modifiedDate']
    search_fields = ['id','comments']
    ordering = ['-modifiedDate',]
    readonly_fields = ['id','recipientInfo','total','adjustments','taxes','fees','netRevenue','outstandingBalance','creationDate','modifiedDate','links','submissionUser','collectedByUser']
    view_on_site = True

    def emailNotification(self, request, queryset):
        # Allows use of the email view to contact specific customers.
        selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect(reverse('sendInvoiceNotifications') + "?invoices=%s" % (",".join(selected)))
    emailNotification.short_description = _('Send email notifications for selected invoices')

    actions = ['emailNotification',]

    def recipientInfo(self,obj):
        if obj.firstName and obj.lastName and obj.email:
            return '%s %s: %s' % (obj.firstName, obj.lastName, obj.email)
        elif obj.email:
            return obj.email
    recipientInfo.short_description = _('Recipient')

    def viewInvoiceLink(self,obj):
        if obj.id:
            change_url = reverse('viewInvoice', args=(obj.id,))
            return mark_safe('<a class="btn btn-outline-secondary" href="%s">View Invoice</a>' % (change_url,))
    viewInvoiceLink.allow_tags = True
    viewInvoiceLink.short_description = _('Invoice')

    def notificationLink(self,obj):
        if obj.id:
            change_url = reverse('sendInvoiceNotifications', args=(obj.id,))
            return mark_safe('<a class="btn btn-outline-secondary" href="%s">Notify Recipient</a>' % (change_url,))
    notificationLink.allow_tags = True
    notificationLink.short_description = _('Invoice notification')

    def finalRegistrationLink(self,obj):
        if obj.finalRegistration:
            change_url = reverse('admin:core_registration_change', args=(obj.finalRegistration.id,))
            return mark_safe('<a class="btn btn-outline-secondary" href="%s">Registration</a>' % (change_url,))
    finalRegistrationLink.allow_tags = True
    finalRegistrationLink.short_description = _('Final registration')

    def temporaryRegistrationLink(self,obj):
        if obj.temporaryRegistration:
            change_url = reverse('admin:core_temporaryregistration_change', args=(obj.temporaryRegistration.id,))
            return mark_safe('<a class="btn btn-outline-secondary" href="%s">Temporary Registration</a>' % (change_url,))
    temporaryRegistrationLink.allow_tags = True
    temporaryRegistrationLink.short_description = _('Temporary registration')

    def links(self,obj):
        return mark_safe(''.join([
            self.viewInvoiceLink(obj) or '',
            self.notificationLink(obj) or '',
            self.temporaryRegistrationLink(obj) or '',
            self.finalRegistrationLink(obj) or '',
        ]))
    links.allow_tags = True
    links.short_description = _('Links')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.submissionUser = request.user
        super(InvoiceAdmin, self).save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        '''
        Update the Invoice object after saving so that the invoice lines
        match the invoice item lines.
        '''
        super(InvoiceAdmin, self).save_related(request, form, formsets, change)
        invoice = form.instance
        for attr in ['grossTotal','total','adjustments','taxes','fees']:
            setattr(invoice,attr,sum([getattr(x,attr) for x in invoice.invoiceitem_set.all()]))
        invoice.save()

    def get_fieldsets(self,request,obj=None):
        if not obj:
            return self.add_fieldsets
        else:
            return super(InvoiceAdmin,self).get_fieldsets(request,obj)

    fieldsets = (
        (None, {
            'fields': ('id',('firstName','lastName','email'),'comments','status','amountPaid','outstandingBalance','links'),
        }),
        (_('Financial Details'), {
            'classes': ('collapse',),
            'fields': ('total','adjustments','taxes','fees','netRevenue'),
        }),
        (_('Dates'), {
            'classes': ('collapse',),
            'fields': ('creationDate','modifiedDate'),
        }),
        (_('Additional data'), {
            'classes': ('collapse',),
            'fields': ('submissionUser','collectedByUser','data'),
        }),
    )

    add_fieldsets = (
        (None, {
            'fields': (('firstName','lastName','email'),'comments','status','amountPaid',),
        }),
        (_('Additional data'), {
            'classes': ('collapse',),
            'fields': ('data',),
        }),
    )


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    inlines = [EventRegistrationInline]
    list_display = ['customer','dateTime','priceWithDiscount','student']
    list_filter = ['dateTime','student','invoice__paidOnline']
    search_fields = ['=customer__first_name','=customer__last_name','customer__email']
    ordering = ('-dateTime',)
    fields = ('customer_link','priceWithDiscount','student','dateTime','comments','howHeardAboutUs')
    readonly_fields = ('customer_link',)

    def customer_link(self,obj):
        change_url = reverse('admin:core_customer_change', args=(obj.customer.id,))
        return mark_safe('<a href="%s">%s</a>' % (change_url, obj.customer))

    customer_link.allow_tags = True
    customer_link.short_description = _("Customer")

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            if not hasattr(instance,'customer'):
                instance.customer = instance.registration.customer
            instance.save()
        formset.save_m2m()


class TemporaryEventRegistrationInline(admin.StackedInline):
    model = TemporaryEventRegistration
    extra = 0

    # These ensure that registration changes happen through the regular registration
    # process.
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TemporaryRegistration)
class TemporaryRegistrationAdmin(admin.ModelAdmin):
    inlines = [TemporaryEventRegistrationInline,]

    list_display = ('__str__','student','dateTime','expirationDate')
    search_fields = ('=firstName','=lastName','email')
    list_filter = ('dateTime','expirationDate',)


######################################
# Miscellaneous Admin classes

@admin.register(ClassDescription)
class ClassDescriptionAdmin(FrontendEditableAdminMixin, admin.ModelAdmin):
    list_display = ['title','danceTypeLevel','oneTimeSeries']
    list_filter = ('danceTypeLevel','oneTimeSeries')
    list_editable = ('oneTimeSeries',)
    search_fields = ('title',)
    prepopulated_fields = {"slug": ("title",)}


class CustomerRegistrationInline(admin.StackedInline):
    model = Registration
    fields = ('registration_link','eventregistration_list')
    readonly_fields = ('registration_link','eventregistration_list')
    extra = 0

    def registration_link(self,obj):
        change_url = reverse('admin:core_registration_change', args=(obj.id,))
        if obj.dateTime:
            return mark_safe('%s: <a href="%s">%s</a>' % (obj.dateTime.strftime('%b. %d, %Y'), change_url, obj.__str__()))
        else:
            return mark_safe('<a href="%s">%s</a>' % (change_url, obj.__str__()))

    registration_link.short_description = _('Registration')
    registration_link.allow_tags = True

    def eventregistration_list(self,obj):
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
                this_string += '%s %s, %s</li>' % (month_name[ereg.event.month], ereg.event.year, ereg.event.name)
            else:
                this_string += '%s</li>' % ereg.event.name
            return_string += this_string
        return return_string
    eventregistration_list.short_description = _('Event Registrations')
    eventregistration_list.allow_tags = True

    # Prevents adding new registrations without going through
    # the standard registration process
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('fullName','numClassSeries','numPublicEvents')
    search_fields = ('=first_name','=last_name','email')
    readonly_fields = ('data','numClassSeries','numPublicEvents')

    fieldsets = (
        (None, {
            'fields': (('first_name','last_name'),'email','phone','user',)
        }),
        (_('Groups'), {
            'fields': ('groups',)
        }),
        (_('Additional Customer Data'), {
            'classes': ('collapse',),
            'fields': (('numClassSeries','numPublicEvents',),'data',),
        }),
    )

    def emailCustomers(self, request, queryset):
        # Allows use of the email view to contact specific customers.
        selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect(reverse('emailStudents') + "?customers=%s" % (",".join(selected)))
    emailCustomers.short_description = _('Email selected customers')

    inlines = [CustomerRegistrationInline,]
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
        super(CustomerGroupAdminForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['customers'] = self.instance.customer_set.values_list('pk', flat=True)

    def save(self, *args, **kwargs):
        instance = super(CustomerGroupAdminForm, self).save(*args, **kwargs)
        if instance.pk:
            instance.customer_set.clear()
            instance.customer_set.add(*self.cleaned_data['customers'])
        return instance

    class Meta:
        model = CustomerGroup
        exclude = []


@admin.register(CustomerGroup)
class CustomerGroupAdmin(admin.ModelAdmin):
    list_display = ('name','memberCount')
    readonly_fields = ('memberCount',)
    form = CustomerGroupAdminForm

    def emailCustomers(self, request, queryset):
        # Allows use of the email view to contact specific customer groups.
        selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect(reverse('emailStudents') + "?customergroup=%s" % (",".join(selected)))
    emailCustomers.short_description = _('Email selected customer groups')

    actions = ['emailCustomers']


@admin.register(EventSession)
class EventSessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'startTime', 'endTime')
    ordering = ('startTime','name')
    readonly_fields = ('startTime','endTime')
    list_filter = ('startTime','endTime')
    prepopulated_fields = {'slug': ('name',)}

    fields = ('name', 'description', 'slug',('startTime','endTime'))


class RoomInline(admin.StackedInline):
    model = Room
    extra = 0
    fields = (('name', 'defaultCapacity'),'description')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    inlines = []

    list_display = ('name','location','defaultCapacity')
    list_display_links = ('name',)
    list_editable = ('defaultCapacity',)
    list_filter = ('location',)

    ordering = ('location__name','name')

    fields = ('location','name','defaultCapacity','description')


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    inlines = [RoomInline,]

    list_display = ('name','address','city','orderNum','status')
    list_display_links = ('name',)
    list_editable = ('orderNum','status')
    list_filter = ('status','city')

    ordering = ('status','orderNum')

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
                'roomOptions': json.dumps([{'id': x.id, 'name': x.name, 'defaultCapacity': x.defaultCapacity} for x in obj.room_set.all()]),
            })

            # Return a modified template
            return SimpleTemplateResponse('core/admin/location_popup_response.html', {
                'popup_response_data': popup_response_data,
            })

        # Otherwise just use the standard ModelAdmin method
        return super(LocationAdmin,self).response_add(request, obj, post_url_continue)

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
            value = request.resolver_match.args[0]
            new_value = obj.serializable_value(attr)
            popup_response_data = json.dumps({
                'action': 'change',
                'value': six.text_type(value),
                'obj': six.text_type(obj),
                'new_value': six.text_type(new_value),
                # Add this extra data
                'defaultCapacity': obj.defaultCapacity,
                'roomOptions': json.dumps([{'id': x.id, 'name': x.name, 'defaultCapacity': x.defaultCapacity} for x in obj.room_set.all()]),
            })

            # Return a modified template
            return SimpleTemplateResponse('core/admin/location_popup_response.html', {
                'popup_response_data': popup_response_data,
            })
        return super(LocationAdmin,self).response_change(request, obj)


@admin.register(PricingTier)
class PricingTierAdmin(admin.ModelAdmin):
    list_display = ('name','expired')
    list_filter = ('expired',)

    # Need to specify an empty list of inlines so that discounts app can add to the list if it is enabled.
    inlines = []


class EmailTemplateAdminForm(ModelForm):

    class Meta:
        model = EmailTemplate
        exclude = []

        widgets = {
            'richTextChoice': RadioSelect,
        }

    class Media:
        js = ('js/emailtemplate_contenttype.js',)


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    form = EmailTemplateAdminForm

    list_display = ('name','richTextChoice','hideFromForm')
    list_filter = ('richTextChoice','groupRequired','hideFromForm')
    ordering = ('name',)

    fieldsets = (
        (None,{
            'fields': ('name','richTextChoice','subject',),
        }),
        (_('Plain text content'),{
            'fields': ('content',),
        }),
        (_('Rich text HTML content'),{
            'fields': ('html_content',),
        }),
        (None,{
            'fields': ('defaultFromName','defaultFromAddress','defaultCC','groupRequired','hideFromForm'),
        }),
    )


######################################
# Staff and subclass admins


class StaffMemberChildAdmin(PolymorphicChildModelAdmin):
    '''
    Base admin class for all child models
    '''
    base_model = StaffMember
    base_fieldsets = (
        (None, {
            'fields': ('firstName','lastName','userAccount',)
        }),
        (_('Contact'), {
            'fields': ('publicEmail','privateEmail','phone'),
        }),
        (_('Bio/Photo'), {
            'fields': ('image','bio'),
        })
    )


@admin.register(Instructor)
class InstructorAdmin(FrontendEditableAdminMixin, StaffMemberChildAdmin):
    base_model = Instructor
    show_in_index = True

    # Allows overriding from other apps
    actions = []
    inlines = []

    list_display = ('fullName','privateEmail','availableForPrivates','status')
    list_display_links = ('fullName',)
    list_editable = ('availableForPrivates','privateEmail','status')
    list_filter = ('status','availableForPrivates')
    search_fields = ('=firstName','=lastName','publicEmail','privateEmail')
    inlines = []

    ordering = ('status','lastName','firstName')

    class Media:
        js = ('bootstrap/js/bootstrap.min.js',)
        css = {'all':('bootstrap/css/bootstrap.min.css',)}


@admin.register(StaffMember)
class StaffMemberParentAdmin(PolymorphicParentModelAdmin):
    '''
    The parent model admin for Staff members
    '''
    base_model = StaffMember
    child_models = (Instructor,)
    list_filter = (PolymorphicChildModelFilter,)

    # Allows overriding from other apps
    inlines = []
    actions = []


######################################
# Event and subclass admins


class EventChildAdmin(PolymorphicChildModelAdmin):
    '''
    Base admin class for all child models
    '''
    base_model = Event

    readonly_fields = ['uuidLink',]

    actions = [repeat_events,]

    def uuidLink(self,obj):
        address = reverse('singleClassRegistration', args=[obj.uuid,])
        return mark_safe('<a href="%s">%s</a>' % (address, address))
    uuidLink.short_description = _('Direct Registration Link')
    uuidLink.allow_tags = True

    # This is needed so that when an event is created, the year and month
    # are properly set right away.
    def save_related(self, request, form, formsets, change):
        obj = form.instance
        super(EventChildAdmin, self).save_related(request, form, formsets, change)

        if obj.eventoccurrence_set.all():
            obj.year = obj.getYearAndMonth()[0]
            obj.month = obj.getYearAndMonth()[1]
            obj.startTime = obj.eventoccurrence_set.order_by('startTime').first().startTime
            obj.endTime = obj.eventoccurrence_set.order_by('endTime').last().endTime
            obj.duration = sum([x.duration for x in obj.eventoccurrence_set.all() if not x.cancelled])
            obj.save()


class SeriesAdminForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super(SeriesAdminForm,self).__init__(*args,**kwargs)

        # Series have registration enabled by default
        self.fields['status'].initial = Event.RegStatus.enabled

        # Locations are required for Series even though they are not for all events.
        self.fields['location'].required = True

        # Allow adding additional rooms from a popup on Location, but not a popup on Room
        self.fields['room'].widget.can_add_related = False
        self.fields['room'].widget.can_change_related = False

        # Impose restrictions on new records, but not on existing ones.
        if not kwargs.get('instance',None):
            # Filter out former locations for new records
            self.fields['location'].queryset = Location.objects.exclude(status=Location.StatusChoices.former)

            # Filter out Pricing Tiers that are expired (i.e. no longer in use)
            self.fields['pricingTier'].queryset = PricingTier.objects.filter(expired=False)

            # Filter out one-time class descriptions
            self.fields['classDescription'].queryset = ClassDescription.objects.filter(oneTimeSeries=False)

            # Set initial values for capacity here because they will automatically update if the
            # constant is changed.  Through Javascript, this should also change when the Location is changed.
            self.fields['capacity'].initial = getConstant(name='registration__defaultEventCapacity')

    # Use the custom location capacity widget to ensure that Javascript can update location specific capacities.
    class Meta:
        model = Series
        exclude = []
        widgets = {
            'location': LocationWithDataWidget,
        }

    class Media:
        js = ('js/serieslocation_capacity_change.js','js/location_related_objects_lookup.js')


@admin.register(Series)
class SeriesAdmin(FrontendEditableAdminMixin, EventChildAdmin):
    base_model = Series
    form = SeriesAdminForm
    show_in_index = True

    inlines = [EventRoleInline,EventOccurrenceInline,SeriesTeacherInline,SubstituteTeacherInline,EventStaffMemberInline]
    list_display = ('name','series_month','location','class_time','status','registrationOpen','pricingTier','category','session','customers')
    list_editable = ('status','category','session')
    list_filter = ('location','status','registrationOpen','category','session','pricingTier')

    def customers(self,obj):
        return obj.numRegistered
    customers.short_description = _('# Registered Students')

    def series_month(self,obj):
        return '%s %s' % (month_name[obj.month or 0],obj.year or '')

    def class_time(self, obj):
        return obj.startTime.strftime('%A, %I:%M %p')

    fieldsets = (
        (None, {
            'fields': ('classDescription',('location','room'),'pricingTier',('category','session','allowDropins'),('uuidLink',)),
        }),
        (_('Override Display/Registration/Capacity'), {
            'classes': ('collapse',),
            'fields': ('status','closeAfterDays','capacity',),
        }),
    )

    # This allows us to save the obj reference in order to process related objects in an inline (substitute teachers)
    def get_form(self, request, obj=None, **kwargs):
        # just save obj reference for future processing in Inline
        request._obj_ = obj
        return super(SeriesAdmin, self).get_form(request, obj, **kwargs)

    def save_model(self,request,obj,form,change):
        obj.submissionUser = request.user
        obj.save()


class PublicEventAdminForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super(PublicEventAdminForm,self).__init__(*args,**kwargs)

        self.fields['status'].initial = Event.RegStatus.disabled

        # Allow adding additional rooms from a popup on Location, but not a popup on Room
        self.fields['room'].widget.can_add_related = False
        self.fields['room'].widget.can_change_related = False

        # Impose restrictions on new records, but not on existing ones.
        if not kwargs.get('instance',None):
            # Filter out former locations
            self.fields['location'].queryset = Location.objects.exclude(status=Location.StatusChoices.former)

            # Filter out Pricing Tiers that are expired (i.e. no longer in use)
            self.fields['pricingTier'].queryset = PricingTier.objects.filter(expired=False)

            # Set initial values for capacity here because they will automatically update if the
            # constant is changed
            self.fields['capacity'].initial = getConstant(name='registration__defaultEventCapacity')

    # Use the custom location capacity widget to ensure that Javascript can update location specific capacities.
    class Meta:
        model = PublicEvent
        exclude = ['month','year','startTime','endTime','duration','submissionUser','registrationOpen']
        widgets = {
            'location': LocationWithDataWidget,
            'submissionUser': HiddenInput(),
        }

    class Media:
        js = ('js/location_related_objects_lookup.js',)


@admin.register(PublicEvent)
class PublicEventAdmin(FrontendEditableAdminMixin, EventChildAdmin):
    base_model = PublicEvent
    form = PublicEventAdminForm
    show_in_index = True

    list_display = ('name','numOccurrences','firstOccurrenceTime','lastOccurrenceTime','location','status','registrationOpen','pricingTier','category','session','numRegistered')
    list_filter = ('location','status','registrationOpen','pricingTier','category','session')
    list_editable = ('status','category','session')
    search_fields = ('name',)
    ordering = ('-endTime',)
    prepopulated_fields = {'slug': ('title',)}
    inlines = [EventRoleInline,EventOccurrenceInline,EventStaffMemberInline]

    fieldsets = (
        (None, {
            'fields': ('title','slug','category','session',('location','room'),)
        }),
        (_('Registration/Visibility'), {
            'fields': ('status',('pricingTier','capacity'),),
        }),
        (_('Description/Link'), {'fields': ('descriptionField','shortDescriptionField','link')})
    )

    # This allows us to save the obj reference in order to process related objects in an inline (substitute teachers)
    def get_form(self, request, obj=None, **kwargs):
        # just save obj reference for future processing in Inline
        request._obj_ = obj
        return super(PublicEventAdmin, self).get_form(request, obj, **kwargs)

    def save_model(self,request,obj,form,change):
        obj.submissionUser = request.user
        obj.save()


@admin.register(Event)
class EventParentAdmin(PolymorphicParentModelAdmin):
    '''
    The parent model admin for Events
    '''
    list_display = ('name','firstOccurrenceTime','lastOccurrenceTime','location','status','registrationOpen')

    base_model = Event
    child_models = (Series,PublicEvent)
    list_filter = (PolymorphicChildModelFilter,'status','registrationOpen','location')
    list_editable = ('status',)
    polymorphic_list = True

    actions = [repeat_events,]


@admin.register(PublicEventCategory)
class PublicEventCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'separateOnRegistrationPage','displayColor']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(SeriesCategory)
class SeriesCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'separateOnRegistrationPage']
    prepopulated_fields = {'slug': ('name',)}


# These admin classes are registered but need nothing additional
admin.site.register(DanceRole)
admin.site.register(DanceType)
admin.site.register(DanceTypeLevel)
admin.site.register(EventStaffCategory)
