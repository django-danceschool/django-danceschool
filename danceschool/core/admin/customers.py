from django.contrib import admin
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.forms import ModelForm, ModelMultipleChoiceField
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from calendar import month_name
from dal import autocomplete

from ..models import Customer, CustomerGroup, EventRegistration


class CustomerEventRegistrationInline(admin.StackedInline):
    model = EventRegistration
    fields = ('registration_link', 'eventregistration_details')
    readonly_fields = ('registration_link', 'eventregistration_details')
    extra = 0

    def registration_link(self, obj):
        change_url = reverse('admin:core_registration_change', args=(obj.registration.id, ))
        if obj.registration.dateTime:
            return mark_safe(
                '%s: <a href="%s">%s</a>' % (
                    obj.registration.dateTime.strftime('%b. %d, %Y'), change_url, obj.registration.__str__()
                )
            )
        else:
            return mark_safe('<a href="%s">%s</a>' % (change_url, obj.registration.__str__()))

    registration_link.short_description = _('Registration')
    registration_link.allow_tags = True

    def eventregistration_details(self, obj):
        return_string = ''
        if obj.cancelled:
            return_string += '<em>%s</em> ' % _('CANCELLED:')
        if obj.dropIn:
            return_string += '<em>%s</em> ' % _('DROP-IN:')
        if obj.event.month:
            return_string += '%s %s, %s</li>' % (
                month_name[obj.event.month], obj.event.year, obj.event.name
            )
        else:
            return_string += obj.event.name
        return mark_safe(return_string)
    eventregistration_details.short_description = _('Details')
    eventregistration_details.allow_tags = True

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
        return qs.filter(registration__final=True)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('fullName', 'numClassSeries', 'numPublicEvents')
    search_fields = ('^first_name', '^last_name', 'email')
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

    inlines = [CustomerEventRegistrationInline, ]
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
