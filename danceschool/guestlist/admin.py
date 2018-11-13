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


admin.site.register(GuestList, GuestListAdmin)
