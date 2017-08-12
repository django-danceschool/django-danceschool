from django.contrib import admin
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from django.utils.html import format_html_join

from danceschool.core.models import Customer
from .models import Requirement, RequirementItem, CustomerRequirement


class RequirementItemInline(admin.TabularInline):
    model = RequirementItem
    extra = 0


class CustomerRequirementInline(admin.StackedInline):
    model = CustomerRequirement
    extra = 0
    readonly_fields = ['submissionDate','modifiedDate']


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    inlines = [RequirementItemInline,]
    readonly_fields = ['submissionDate','modifiedDate','customerMeetsListing','customerDoesNotMeetListing']
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
            'fields': ('customerMeetsListing','customerDoesNotMeetListing'),
        }),
        (_('Date and Time'), {
            'classes': ('collapse',),
            'fields': ('submissionDate','modifiedDate'),
        })
    )

    def customerMeetsListing(self,obj):
        ''' Provide a list of customers meeting the requirement '''
        return format_html_join(
            '\n','<a href="{}">{}</a><br />',
            [
                (reverse('admin:core_customer_change', args=(customer.id,)),customer.fullName)
                for customer in obj.customerrequirement_set.filter(met=True)
            ]
        )
    customerMeetsListing.allow_tags = True
    customerMeetsListing.short_description = _('Customers explicitly meeting requirement')

    def customerDoesNotMeetListing(self,obj):
        ''' Provide a list of customers meeting the requirement '''
        return format_html_join(
            '\n','<a href="{}">{}</a><br />',
            [
                (reverse('admin:core_customer_change', args=(customer.id,)),customer.fullName)
                for customer in obj.customerrequirement_set.filter(met=False)
            ]
        )
    customerDoesNotMeetListing.allow_tags = True
    customerDoesNotMeetListing.short_description = _('Customers explicitly not meeting requirement')



admin.site._registry[Customer].inlines.insert(0,CustomerRequirementInline)
