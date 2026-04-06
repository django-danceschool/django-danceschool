from django.contrib import admin
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from polymorphic.admin import (
    PolymorphicParentModelAdmin, PolymorphicChildModelAdmin,
    PolymorphicChildModelFilter
)

from ..models import Event, Series, PublicEvent


# For split date/time fields
WIDGET_FORMATS = ['%I:%M%p', '%I:%M %p', '%I:%M', '%H:%M:%S', '%H:%M']


######################################
# Admin action for repeating events


def repeat_events(modeladmin, request, queryset):
    selected = request.POST.getlist(ACTION_CHECKBOX_NAME)
    ct = ContentType.objects.get_for_model(queryset.model)
    return HttpResponseRedirect(reverse('repeatEvents') + "?ct=%s&ids=%s" % (ct.pk, ", ".join(selected)))


repeat_events.short_description = _('Duplicate selected events')


class EventChildAdmin(PolymorphicChildModelAdmin):
    '''
    Base admin class for all child models
    '''
    base_model = Event

    readonly_fields = ['uuidLink', ]

    actions = [repeat_events, ]

    uuid_link_view_name = 'eventViewUUID'

    def uuidLink(self, obj):
        address = reverse(self.uuid_link_view_name, args=[obj.uuid, ])
        return mark_safe('<a href="%s">%s</a>' % (address, address))
    uuidLink.short_description = _('Direct Registration Link')
    uuidLink.allow_tags = True


@admin.register(Event)
class EventParentAdmin(PolymorphicParentModelAdmin):
    '''
    The parent model admin for Events
    '''
    list_display = (
        'name', 'firstOccurrenceTime', 'lastOccurrenceTime', 'location',
        'status', 'registrationOpen'
    )

    base_model = Event
    child_models = (Series, PublicEvent)
    list_filter = (PolymorphicChildModelFilter, 'status', 'registrationOpen', 'location')
    list_editable = ('status', )
    polymorphic_list = True
    search_fields = ('name', )

    actions = [repeat_events, ]
