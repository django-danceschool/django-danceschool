from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from rangefilter.filters import DateRangeFilter

from ..models import PublicEventCategory, SeriesCategory, EventSession


@admin.register(PublicEventCategory)
class PublicEventCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'separateOnRegistrationPage', 'displayColor']
    prepopulated_fields = {'slug': ('name', )}


@admin.register(SeriesCategory)
class SeriesCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'separateOnRegistrationPage']
    prepopulated_fields = {'slug': ('name', )}


@admin.register(EventSession)
class EventSessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'startTime', 'endTime')
    ordering = ('startTime', 'name')
    readonly_fields = ('startTime', 'endTime')
    list_filter = (('startTime', DateRangeFilter), ('endTime', DateRangeFilter))
    prepopulated_fields = {'slug': ('name', )}

    fields = ('name', 'description', 'slug', ('startTime', 'endTime'))
