from django.contrib import admin
from django.forms import ModelForm, ModelChoiceField
from django.utils.translation import gettext_lazy as _

from cms.admin.placeholderadmin import FrontendEditableAdminMixin
from django_admin_listfilter_dropdown.filters import RelatedDropdownFilter
from dal import autocomplete
from functools import partialmethod

from ..models import StaffMember, Instructor, EventStaffMember, EventStaffCategory, EventOccurrence


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

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        return super().__init__(*args, **kwargs)

    def save(self, commit=True):
        '''
        Assume that the staffing applies to all occurrences if none were
        otherwise supplied.
        '''
        if not self.cleaned_data.get('occurrences', None):
            self.cleaned_data['occurrences'] = self.instance.event.eventoccurrence_set.all()
        self.instance.submissionUser = self.user
        return super().save(commit=commit)

    class Media:
        js = (
            'admin/js/vendor/jquery/jquery.min.js',
            'admin/js/jquery.init.js',
        )


class EventStaffMemberInline(admin.TabularInline):
    model = EventStaffMember
    exclude = ('submissionUser', 'replacedStaffMember')
    fields = ('staffMember', 'category', 'occurrences', 'specifiedHours')
    extra = 0
    form = EventStaffMemberInlineForm

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)

        if db_field.name == 'occurrences':
            if request._obj_ is not None:
                # set the query set to whatever you like
                field.queryset = EventOccurrence.objects.filter(event=request._obj_)
                if not getattr(self, 'pk', None):
                    field.initial = field.queryset
                    field.required = True
            else:
                field.queryset = field.queryset.none()
        return field

    def get_formset(self, request, obj, **kwargs):
        ''' Add the request to the formset kwargs '''
        formset = super().get_formset(request, obj, **kwargs)
        formset._construct_form = partialmethod(
            formset._construct_form, user=request.user
        )
        return formset


@admin.register(EventStaffCategory)
class EventStaffCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', ]

    # Allows financial app to add default wage inline
    inlines = []


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
    list_filter = (
        ('categories', RelatedDropdownFilter),
        'instructor__status',
        'instructor__availableForPrivates'
    )
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
        js = ('https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/js/bootstrap.bundle.min.js', )
        css = {'all': ('https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css', )}
