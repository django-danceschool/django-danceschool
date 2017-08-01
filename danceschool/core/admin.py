from django.contrib import admin
from django.forms import ModelForm, SplitDateTimeField, HiddenInput, RadioSelect
from django.utils.safestring import mark_safe
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from calendar import month_name
from polymorphic.admin import PolymorphicParentModelAdmin, PolymorphicChildModelAdmin, PolymorphicChildModelFilter
from cms.admin.placeholderadmin import FrontendEditableAdminMixin

from .models import Event, PublicEventCategory, Series, PublicEvent, EventOccurrence, SeriesTeacher, StaffMember, Instructor, SubstituteTeacher, Registration, TemporaryRegistration, EventRegistration, TemporaryEventRegistration, ClassDescription, Customer, Location, PricingTier, DanceRole, DanceType, DanceTypeLevel, EmailTemplate, EventStaffMember, EventStaffCategory, EventRole, Invoice, InvoiceItem
from .constants import getConstant
from .forms import LocationWithCapacityWidget


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
        js = ('timepicker/jquery.timepicker.min.js','jquery-ui/jquery-ui.min.js','js/eventadmin_pickers.js')
        css = {'all':('timepicker/jquery.timepicker.css','jquery-ui/jquery-ui.min.css',)}


######################################
# Registration related admin classes


class InvoiceItemInline(admin.StackedInline):
    model = InvoiceItem
    extra = 0
    fields = ['id','description','grossTotal','adjustments','temporaryEventRegistrationLink','finalEventRegistrationLink']
    readonly_fields = ['id','temporaryEventRegistrationLink','finalEventRegistrationLink']

    # This ensures that InvoiceItems are not deleted except through
    # the regular registration process.  Invoice items can still be
    # manually added.
    def has_delete_permission(self, request, obj=None):
        return False

    def finalEventRegistrationLink(self,obj):
        change_url = reverse('admin:core_eventregistration_change', args=(obj.finalEventRegistration.id,))
        return mark_safe('<a href="%s">#%s</a>' % (change_url, obj.finalEventRegistration.id))
    finalEventRegistrationLink.allow_tags = True
    finalEventRegistrationLink.short_description = _('Final event registration')

    def temporaryEventRegistrationLink(self,obj):
        change_url = reverse('admin:core_temporaryeventregistration_change', args=(obj.temporaryEventRegistration.id,))
        return mark_safe('<a href="%s">#%s</a>' % (change_url, obj.temporaryEventRegistration.id))
    temporaryEventRegistrationLink.allow_tags = True
    temporaryEventRegistrationLink.short_description = _('Temporary event registration')


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    inlines = [InvoiceItemInline,]
    list_display = ['id', 'status', 'total','netRevenue','outstandingBalance','creationDate','modifiedDate','links']
    list_filter = ['status', 'paidOnline', 'creationDate', 'modifiedDate']
    search_fields = ['id','comments']
    ordering = ['-modifiedDate',]
    readonly_fields = ['id','total','adjustments','taxes','fees','netRevenue','outstandingBalance','creationDate','modifiedDate','links','submissionUser','collectedByUser']

    def viewInvoiceLink(self,obj):
        change_url = reverse('viewInvoice', args=(obj.id,))
        return mark_safe('<a class="btn btn-default" href="%s">View Invoice</a>' % (change_url,))
    viewInvoiceLink.allow_tags = True
    viewInvoiceLink.short_description = _('Invoice')

    def finalRegistrationLink(self,obj):
        if obj.finalRegistration:
            change_url = reverse('admin:core_registration_change', args=(obj.finalRegistration.id,))
            return mark_safe('<a class="btn btn-default" href="%s">Registration</a>' % (change_url,))
    finalRegistrationLink.allow_tags = True
    finalRegistrationLink.short_description = _('Final registration')

    def temporaryRegistrationLink(self,obj):
        if obj.temporaryRegistration:
            change_url = reverse('admin:core_temporaryregistration_change', args=(obj.temporaryRegistration.id,))
            return mark_safe('<a class="btn btn-default" href="%s">Temporary Registration</a>' % (change_url,))
    temporaryRegistrationLink.allow_tags = True
    temporaryRegistrationLink.short_description = _('Temporary registration')

    def links(self,obj):
        return ''.join([
            self.viewInvoiceLink(obj) or '',
            self.temporaryRegistrationLink(obj) or '',
            self.finalRegistrationLink(obj) or '',
        ])
    links.allow_tags = True
    links.short_description = _('Links')

    fieldsets = (
        (None, {
            'fields': ('id','status','amountPaid','outstandingBalance','links','comments'),
        }),
        (_('Financial Details'), {
            'fields': ('total','adjustments','taxes','fees','netRevenue'),
        }),
        (_('Dates'), {
            'fields': ('creationDate','modifiedDate'),
        }),
        (_('Additional data'), {
            'classes': ('collapse',),
            'fields': ('submissionUser','collectedByUser','data'),
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
    inlines = [TemporaryEventRegistrationInline]

    list_display = ('__str__','student','dateTime')
    search_fields = ('=firstName','=lastName','email')
    list_filter = ('dateTime',)


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
    list_display = ('__str__','numClassSeries','numPublicEvents')
    search_fields = ('=first_name','=last_name','email')
    readonly_fields = ('data','numClassSeries','numPublicEvents')

    fieldsets = (
        (None, {
            'fields': ('user','numClassSeries','numPublicEvents','phone',)
        }),
        (_('Additional Customer Data'), {
            'classes': ('collapse',),
            'fields': ('data',),
        }),
    )

    inlines = [CustomerRegistrationInline,]


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name','address','city','orderNum','status')
    list_display_links = ('name',)
    list_editable = ('orderNum','status')
    list_filter = ('status','city')

    ordering = ('status','orderNum')


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

    list_display = ('fullName','privateEmail','availableForPrivates','status')
    list_display_links = ('fullName',)
    list_editable = ('availableForPrivates','privateEmail','status')
    list_filter = ('status','availableForPrivates')
    search_fields = ('=firstName','=lastName','publicEmail','privateEmail')

    ordering = ('status','lastName','firstName')

    class Media:
        js = ('bootstrap/js/bootstrap.min.js',)
        css = {'all':('bootstrap/css/bootstrap.min.css',)}


@admin.register(StaffMember)
class StaffMemberParentAdmin(PolymorphicParentModelAdmin):
    '''
    The parent model admin for Events
    '''
    base_model = StaffMember
    child_models = (Instructor,)
    list_filter = (PolymorphicChildModelFilter,)


######################################
# Event and subclass admins

class EventChildAdmin(PolymorphicChildModelAdmin):
    '''
    Base admin class for all child models
    '''
    base_model = Event

    readonly_fields = ['uuidLink',]

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
            'location': LocationWithCapacityWidget,
        }

    class Media:
        js = ('js/serieslocation_capacity_change.js',)


@admin.register(Series)
class SeriesAdmin(FrontendEditableAdminMixin, EventChildAdmin):
    base_model = Series
    form = SeriesAdminForm
    show_in_index = True

    inlines = [EventRoleInline,EventOccurrenceInline,SeriesTeacherInline,SubstituteTeacherInline]
    list_display = ('name','series_month','location','class_time','pricingTier','special','customers')
    list_filter = ('location','special','pricingTier')

    def customers(self,obj):
        return obj.numRegistered
    customers.short_description = _('# Registered Students')

    def series_month(self,obj):
        return '%s %s' % (month_name[obj.month or 0],obj.year or '')

    def class_time(self, obj):
        return obj.startTime.strftime('%A, %I:%M %p')

    fieldsets = (
        (None, {
            'fields': ('classDescription','location','pricingTier',('special','allowDropins'),('uuidLink',)),
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

        # Impose restrictions on new records, but not on existing ones.
        if not kwargs.get('instance',None):
            # Filter out former locations
            self.fields['location'].queryset = Location.objects.exclude(status=Location.StatusChoices.former)

            # Set initial values for capacity here because they will automatically update if the
            # constant is changed
            self.fields['capacity'].initial = getConstant(name='registration__defaultEventCapacity')

    # Use the custom location capacity widget to ensure that Javascript can update location specific capacities.
    class Meta:
        widgets = {
            'location': LocationWithCapacityWidget,
            'submissionUser': HiddenInput(),
        }


@admin.register(PublicEvent)
class PublicEventAdmin(FrontendEditableAdminMixin, EventChildAdmin):
    base_model = PublicEvent
    form = PublicEventAdminForm
    show_in_index = True

    list_display = ('name','numOccurrences','firstOccurrenceTime','lastOccurrenceTime','location','pricingTier','registrationOpen','numRegistered')
    list_filter = ('location','registrationOpen','pricingTier')
    search_fields = ('name',)
    ordering = ('-endTime',)
    prepopulated_fields = {'slug': ('title',)}
    inlines = [EventRoleInline,EventOccurrenceInline,EventStaffMemberInline]
    exclude = ['month','year','startTime','endTime','duration','submissionUser','registrationOpen']

    fieldsets = (
        (None, {
            'fields': ('title','slug','category','location')
        }),
        (_('Registration/Visibility'), {
            'fields': ('status',('pricingTier','capacity'),),
        }),
        (_('Description/Link'), {'fields': ('descriptionField','link')})
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
    list_filter = (PolymorphicChildModelFilter,'status','location')
    polymorphic_list = True


# These admin classes are registered but need nothing additional
admin.site.register(DanceRole)
admin.site.register(DanceType)
admin.site.register(DanceTypeLevel)
admin.site.register(PublicEventCategory)
admin.site.register(EventStaffCategory)
