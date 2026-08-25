from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import (
    GuestList, GuestListRegistrationComponent, GuestListStaffComponent,
    GuestListName
)


class GuestListNameInline(admin.TabularInline):
    model = GuestListName
    extra = 0


class GuestListStaffComponentInline(admin.TabularInline):
    model = GuestListStaffComponent
    extra = 1
    fields = (
        'staffCategory', 'staffMember', 'admissionRule', 'daysBefore', 'daysAfter',
    )


class GuestListRegistrationComponentForm(forms.ModelForm):
    '''
    A component with no qualifying categories would silently admit no one, so
    require at least one.  This cannot be done in the model's clean() method,
    because the submitted categories are not available at that point.
    '''

    class Meta:
        model = GuestListRegistrationComponent
        fields = '__all__'

    def clean(self):
        super().clean()
        if not (
            self.cleaned_data.get('seriesCategories') or
            self.cleaned_data.get('eventCategories')
        ):
            raise ValidationError(_(
                'At least one qualifying series category or public event ' +
                'category must be specified.'
            ))
        return self.cleaned_data


class GuestListRegistrationComponentInline(admin.StackedInline):
    model = GuestListRegistrationComponent
    form = GuestListRegistrationComponentForm
    extra = 0
    filter_horizontal = ('seriesCategories', 'eventCategories')
    fields = (
        ('admissionRule', 'daysBefore', 'daysAfter'),
        'seriesCategories', 'eventCategories',
    )


class GuestListAdmin(admin.ModelAdmin):
    list_display = ('name', 'sortOrder', 'includeStaff', 'includeRegistrants')
    list_filter = ('includeStaff', 'includeRegistrants',)
    inlines = [
        GuestListStaffComponentInline, GuestListRegistrationComponentInline,
        GuestListNameInline,
    ]

    fieldsets = (
        (None, {
            'fields': ('name',),
        }),
        (_('Apply to categories'), {
            'classes': ('collapse',),
            'fields': ('seriesCategories', 'eventCategories'),
        }),
        (_('Apply to sessions'), {
            'classes': ('collapse',),
            'fields': ('eventSessions',),
        }),
        (_('Apply to individual series/events'), {
            'classes': ('collapse',),
            'fields': ('individualEvents',),
        }),
        (None, {
            'fields': ('includeStaff', 'includeRegistrants', 'sortOrder',),
        }),
    )


admin.site.register(GuestList, GuestListAdmin)
