from django.contrib import admin
from django.utils.translation import ugettext_lazy as _
from django.forms import ModelForm

from danceschool.core.admin import EventChildAdmin, EventOccurrenceInline
from danceschool.core.models import Event
from danceschool.core.forms import LocationWithDataWidget

from .models import PrivateEvent, PrivateEventCategory, EventReminder


class EventReminderInline(admin.StackedInline):
    model = EventReminder
    extra = 0


class PrivateEventAdminForm(ModelForm):
    '''
    Custom form for private events is needed to include necessary
    Javascript for room selection, even though capacity is not
    an included field in this admin.
    '''

    class Meta:
        model = PrivateEvent
        exclude = ['month','year','startTime','endTime','duration','submissionUser','registrationOpen','capacity','status']
        widgets = {
            'location': LocationWithDataWidget,
        }

    class Media:
        js = ('js/serieslocation_capacity_change.js','js/location_related_objects_lookup.js')


class PrivateEventAdmin(EventChildAdmin):
    base_model = PrivateEvent
    form = PrivateEventAdminForm
    show_in_index = True

    list_display = ('name','category','nextOccurrenceTime','firstOccurrenceTime','location_given','displayToGroup')
    list_filter = ('category','displayToGroup','location','locationString')
    search_fields = ('title',)
    ordering = ('-endTime',)
    inlines = [EventOccurrenceInline, EventReminderInline]

    fieldsets = (
        (None, {
            'fields': ('title','category','descriptionField','link')
        }),
        ('Location', {
            'fields': (('location','room'),'locationString')
        }),
        ('Visibility', {
            'fields': ('displayToGroup','displayToUsers'),
        })
    )

    def location_given(self,obj):
        if obj.room and obj.location:
            return _('%s, %s' % (obj.room.name, obj.location.name))
        if obj.location:
            return obj.location.name
        return obj.locationString

    def save_model(self,request,obj,form,change):
        obj.status = Event.RegStatus.disabled
        obj.submissionUser = request.user
        obj.save()


admin.site.register(PrivateEvent,PrivateEventAdmin)
admin.site.register(PrivateEventCategory)
