from django.contrib import admin
from django.template.response import SimpleTemplateResponse
import json
import six

from ..models import Room, Location


class RoomInline(admin.StackedInline):
    model = Room
    extra = 0
    fields = (('name', 'defaultCapacity'), 'description')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    inlines = []

    list_display = ('name', 'location', 'defaultCapacity')
    list_display_links = ('name', )
    list_editable = ('defaultCapacity', )
    list_filter = ('location', )

    ordering = ('location__name', 'name')

    fields = ('location', 'name', 'defaultCapacity', 'description')


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    inlines = [RoomInline, ]

    list_display = ('name', 'address', 'city', 'orderNum', 'status')
    list_display_links = ('name', )
    list_editable = ('orderNum', 'status')
    list_filter = ('status', 'city')

    ordering = ('status', 'orderNum')

    def response_add(self, request, obj, post_url_continue=None):
        '''
        This just modifies the normal ModelAdmin process in order to
        pass capacity and room options for the added Location along with
        the location's name and ID.
        '''

        IS_POPUP_VAR = '_popup'
        TO_FIELD_VAR = '_to_field'

        if IS_POPUP_VAR in request.POST:
            to_field = request.POST.get(TO_FIELD_VAR)
            if to_field:
                attr = str(to_field)
            else:
                attr = obj._meta.pk.attname
            value = obj.serializable_value(attr)
            popup_response_data = json.dumps({
                'value': six.text_type(value),
                'obj': six.text_type(obj),
                # Add this extra data
                'defaultCapacity': obj.defaultCapacity,
                'roomOptions': json.dumps([
                    {'id': x.id, 'name': x.name, 'defaultCapacity': x.defaultCapacity} for
                    x in obj.room_set.all()
                ]),
            })

            # Return a modified template
            return SimpleTemplateResponse('core/admin/location_popup_response.html', {
                'popup_response_data': popup_response_data,
            })

        # Otherwise just use the standard ModelAdmin method
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        '''
        This just modifies the normal ModelAdmin process in order to
        pass capacity and room options for the modified Location along with
        the location's name and ID.
        '''

        IS_POPUP_VAR = '_popup'
        TO_FIELD_VAR = '_to_field'

        if IS_POPUP_VAR in request.POST:
            to_field = request.POST.get(TO_FIELD_VAR)
            attr = str(to_field) if to_field else obj._meta.pk.attname
            # Retrieve the `object_id` from the resolved pattern arguments.
            value = request.resolver_match.args[0] if request.resolver_match.args else None
            new_value = obj.serializable_value(attr)
            popup_response_data = json.dumps({
                'action': 'change',
                'value': six.text_type(value),
                'obj': six.text_type(obj),
                'new_value': six.text_type(new_value),
                # Add this extra data
                'defaultCapacity': obj.defaultCapacity,
                'roomOptions': json.dumps([
                    {'id': x.id, 'name': x.name, 'defaultCapacity': x.defaultCapacity} for
                    x in obj.room_set.all()
                ]),
            })

            # Return a modified template
            return SimpleTemplateResponse('core/admin/location_popup_response.html', {
                'popup_response_data': popup_response_data,
            })
        return super().response_change(request, obj)
