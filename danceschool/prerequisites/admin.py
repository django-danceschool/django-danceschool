from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

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
    readonly_fields = ['submissionDate','modifiedDate']
    list_display = ['name','applicableLevel','applicableClass','enforcementMethod']
    list_editable = ['enforcementMethod',]

    fieldsets = (
        (None, {
            'fields': ('name',('applicableLevel','applicableClass'),'booleanRule','enforcementMethod',)
        }),
        (_('Role Options'), {
            'fields': ('roleEnforced','applicableRole'),
        }),
        (_('Date and Time'), {
            'classes': 'collapse',
            'fields': ('submissionDate','modifiedDate'),
        })
    )


admin.site._registry[Customer].inlines.insert(0,CustomerRequirementInline)
