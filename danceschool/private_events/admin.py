from django.contrib import admin

from danceschool.core.admin import EventChildAdmin, EventOccurrenceInline
from danceschool.core.models import Event

from .models import PrivateEvent, PrivateEventCategory, EventReminder


class EventReminderInline(admin.StackedInline):
    model = EventReminder
    extra = 0


class PrivateEventAdmin(EventChildAdmin):
    base_model = PrivateEvent
    show_in_index = True

    list_display = ('name','category','nextOccurrenceTime','firstOccurrenceTime','location_given','displayToGroup')
    list_filter = ('category','displayToGroup','location','locationString')
    search_fields = ('title',)
    ordering = ('-endTime',)
    inlines = [EventOccurrenceInline, EventReminderInline]

    exclude = ['month','year','startTime','endTime','duration','submissionUser','registrationOpen','capacity','status']

    fieldsets = (
        (None, {
            'fields': ('title','category','descriptionField','link')
        }),
        ('Location', {
            'fields': ('location','locationString')
        }),
        ('Visibility', {
            'fields': ('displayToGroup','displayToUsers'),
        })
    )

    def location_given(self,obj):
        if obj.location:
            return obj.location.name
        return obj.locationString

    def save_model(self,request,obj,form,change):
        obj.status = Event.RegStatus.disabled
        obj.submissionUser = request.user
        obj.save()


admin.site.register(PrivateEvent,PrivateEventAdmin)
admin.site.register(PrivateEventCategory)
