from django.contrib import admin

from adminsortable2.admin import SortableInlineAdminMixin

from ..models import EventAddOn


class EventAddOnInline(SortableInlineAdminMixin, admin.TabularInline):
    model = EventAddOn
    extra = 0
    autocomplete_fields = ['addOnEvent',]
    fk_name = 'event'
    classes = ['collapse']
