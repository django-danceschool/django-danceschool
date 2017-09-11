from django.contrib import admin
from django.forms import ModelForm, HiddenInput
from django.utils.translation import ugettext_lazy as _

from .models import InstructorPrivateLessonDetails, InstructorAvailabilitySlot, PrivateLessonEvent, PrivateLessonCustomer

from danceschool.core.models import Instructor, EventStaffMember
from danceschool.core.admin import EventChildAdmin, EventOccurrenceInline, EventRegistrationInline
from danceschool.core.constants import getConstant
from danceschool.core.forms import LocationWithDataWidget


class InstructorPrivateLessonDetailsInline(admin.TabularInline):
    model = InstructorPrivateLessonDetails
    extra = 0

    # Prevents adding new voucher uses without going through
    # the standard registration process
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InstructorAvailabilitySlot)
class InstructorAvailabilitySlotAdmin(admin.ModelAdmin):
    exclude = []


class PrivateLessonCustomerInline(admin.StackedInline):
    model = PrivateLessonCustomer
    extra = 0


class PrivateLessonTeacherInlineForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(PrivateLessonTeacherInlineForm,self).__init__(*args,**kwargs)

        self.fields['staffMember'].label = _('Instructor')
        self.fields['category'].initial = getConstant('privateLessons__eventStaffCategoryPrivateLesson').id

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


class PrivateLessonTeacherInline(admin.StackedInline):
    model = EventStaffMember
    form = PrivateLessonTeacherInlineForm
    exclude = ('replacedStaffMember','occurrences','submissionUser')
    extra = 0

    def save_model(self,request,obj,form,change):
        obj.replacedStaffMember = None
        obj.occurrences = obj.event.eventoccurrence_set.all()
        obj.submissionUser = request.user
        obj.save()


class PrivateLessonEventRegistrationInline(EventRegistrationInline):
    ''' View/edit but do not add/delete EventRegistrations from here. '''
    fields = ['role','cancelled','price','netPrice']
    readonly_fields = ['price','netPrice']


class PrivateLessonEventAdminForm(ModelForm):
    '''
    Custom form for private lesson events is needed to include necessary
    Javascript for room selection, even though capacity is not
    an included field in this admin.
    '''

    class Meta:
        model = PrivateLessonEvent
        exclude = ['month','year','startTime','endTime','duration','submissionUser','registrationOpen','capacity','status']
        widgets = {
            'location': LocationWithDataWidget,
        }

    class Media:
        js = ('js/serieslocation_capacity_change.js','js/location_related_objects_lookup.js')


@admin.register(PrivateLessonEvent)
class PrivateLessonEventAdmin(EventChildAdmin):
    base_model = PrivateLessonEvent
    form = PrivateLessonEventAdminForm
    show_in_index = True

    list_display = ('teacherNames','customerNames','startTime','durationMinutes','location','pricingTier')
    list_filter = ('location','room','startTime','pricingTier')

    fieldsets = (
        (None, {'fields': (('location','room'),'pricingTier','participants','comments',)}),
    )

    def teacherNames(self,obj):
        return ', '.join([x.staffMember.fullName for x in obj.eventstaffmember_set.all()])
    teacherNames.short_description = _('Instructors')

    def customerNames(self,obj):
        return ', '.join([x.fullName for x in obj.customers])
    customerNames.short_description = _('Customers')

    inlines = [EventOccurrenceInline,PrivateLessonCustomerInline,PrivateLessonTeacherInline,PrivateLessonEventRegistrationInline]


admin.site._registry[Instructor].inlines.insert(0,InstructorPrivateLessonDetailsInline)
