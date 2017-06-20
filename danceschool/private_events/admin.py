from django.contrib import admin
from django.forms import ModelForm, SplitDateTimeField
from django.utils.translation import ugettext_lazy as _

from danceschool.core.admin import EventChildAdmin
from danceschool.core.models import EventOccurrence, Event

from .models import PrivateEvent, PrivateEventCategory, EventReminder

# Register your models here.


class EventOccurrenceInlineForm(ModelForm):
    startTime = SplitDateTimeField(required=True,label=_('Start Date/Time'))
    endTime = SplitDateTimeField(required=True,label=_('End Date/Time'))


class EventReminderInline(admin.StackedInline):
    model = EventReminder
    extra = 0


class EventOccurrenceInline(admin.TabularInline):
    model = EventOccurrence
    form = EventOccurrenceInlineForm
    extra = 1

    class Media:
        js = ('timepicker/jquery.timepicker.min.js','jquery-ui/jquery-ui.min.js','js/eventadmin_pickers.js')
        css = {'all':('timepicker/jquery.timepicker.css','jquery-ui/jquery-ui.min.css',)}


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
