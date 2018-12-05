from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

from .models import GuestList, GuestListComponent, GuestListName


class GuestListNameInline(admin.TabularInline):
    model = GuestListName
    extra = 0


class GuestListComponentInline(admin.TabularInline):
    model = GuestListComponent
    extra = 1


class GuestListAdmin(admin.ModelAdmin):
    list_display = ('name','sortOrder','includeStaff','includeRegistrants')
    list_filter = ('includeStaff','includeRegistrants',)
    inlines = [GuestListComponentInline, GuestListNameInline]

    fieldsets = (
        (None, {
            'fields': ('name',),
        }),
        (_('Apply to categories'), {
            'classes': ('collapse',),
            'fields': ('seriesCategories','eventCategories'),
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
            'fields': ('includeStaff','includeRegistrants','sortOrder',),
        }),
    )


admin.site.register(GuestList, GuestListAdmin)
