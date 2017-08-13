from django.contrib import admin
from django.forms import ModelForm, ModelChoiceField
from django.utils.translation import ugettext_lazy as _
from django.utils.html import format_html

from dal import autocomplete

from danceschool.core.models import Customer
from .models import Requirement, RequirementItem, CustomerRequirement


class RequirementItemInline(admin.TabularInline):
    model = RequirementItem
    extra = 0
    verbose_name_plural = _('Requirement items (leave blank for requirement by audition only)')


class CustomerRequirementInline(admin.StackedInline):
    model = CustomerRequirement
    extra = 0
    readonly_fields = ['submissionDate','modifiedDate']
    classes = ('collapse',)


class RequirementAdminForm(ModelForm):
    customerCheck = ModelChoiceField(
        label=_('Search for customer'),
        queryset=Customer.objects.all(),
        required=False,
        widget=autocomplete.ModelSelect2(
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

    class Meta:
        model = Requirement
        exclude = []


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    form = RequirementAdminForm
    inlines = [RequirementItemInline,]
    readonly_fields = ['submissionDate','modifiedDate','customerAjaxDiv']
    list_display = ['name','applicableLevel','applicableClass','enforcementMethod']
    list_editable = ['enforcementMethod',]

    fieldsets = (
        (None, {
            'fields': ('name',('applicableLevel','applicableClass'),'booleanRule','enforcementMethod',)
        }),
        (_('Role Options'), {
            'classes': ('collapse',),
            'fields': ('roleEnforced','applicableRole'),
        }),
        (_('Customers Meeting Requirement'),{
            'classes': ('collapse',),
            'fields': ('customerCheck','customerAjaxDiv'),
        }),
        (_('Date and Time'), {
            'classes': ('collapse',),
            'fields': ('submissionDate','modifiedDate'),
        })
    )

    def customerAjaxDiv(self,obj):
        '''
        This creates a div in which it will be shown whether a customer meets or does not meet
        the requirement, and in which it is possible to explicitly give or deny a requirement for
        a specific customer. All of the actual work is done in the Javascript file which is
        contained in the overridden change_form.html for this model.
        '''
        return format_html(
            '<p><div id="customerrequirement_ajax_div" data-requirementId="{}"></div></p>' +
            '<p><div id="customerrequirement_buttons_div">' +
            '<button class="btn customerrequirement_change" data-met="true">{}</button>' +
            '<button class="btn customerrequirement_change" data-met="false">{}</button></div></p>',
            obj.id,
            _('Requirement is met'),
            _('Requirement is not met'),
        )
    customerAjaxDiv.allow_tags = True
    customerAjaxDiv.short_description = _('Requirement status')


admin.site._registry[Customer].inlines.insert(0,CustomerRequirementInline)
