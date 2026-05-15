from django import forms
from django.forms.widgets import Select
from django.utils.translation import gettext_lazy as _

import json
import logging

from ..models import Series, Location
from ..utils.timezone import ensure_localtime


# Define logger for this file
logger = logging.getLogger(__name__)



class LocationWithDataWidget(Select):
    '''
    Override create_option to add data-defaultCapacity and data-roomOptions
    attributes to each location option, used by serieslocation_capacity_change.js.
    '''

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        option_value = value.value if hasattr(value, 'value') else value
        if option_value:
            this_location = Location.objects.filter(id=int(option_value)).first()
            if this_location:
                option['attrs']['data-defaultCapacity'] = this_location.defaultCapacity
                option['attrs']['data-roomOptions'] = json.dumps([
                    {'id': x.id, 'name': x.name, 'defaultCapacity': x.defaultCapacity}
                    for x in this_location.room_set.all()
                ])

        return option


class EventCheckboxInput(forms.CheckboxInput):
    template_name = 'core/registration/event_checkbox_input.html'


class EventQuantityInput(forms.NumberInput):
    template_name = 'core/registration/event_number_input.html'


class EventChoiceMultiWidget(forms.MultiWidget):
    '''
    This widget handles the logic for the inclusion of the event registration
    information as multiple separate inputs (one per role plus drop-ins)
    '''

    template_name = 'core/registration/event_choice_widget.html'

    def __init__(self, **kwargs):
        self.choices = kwargs.pop('choices', [])
        field_type = kwargs.pop('field_type', forms.BooleanField)
        self.input_type = EventCheckboxInput if field_type == forms.BooleanField else EventQuantityInput

        widgets = {}

        for x in self.choices:
            attrs = x.copy()
            value = attrs.pop('value', '')
            capacity_override = attrs.pop('data-capacity-override', False)

            if self.input_type == EventQuantityInput:
                attrs['min'] = 0
                attrs['max'] = attrs.get('data-capacity', 100) - attrs.get('data-num-registered', 0)
                if capacity_override:
                    attrs['max'] = 100
            widgets[value] = self.input_type(attrs=attrs)

        super().__init__(widgets=widgets, **kwargs)

    def get_context(self, name, value, attrs):
        ''' Separate out additional choices from baseline choices '''
        context = super().get_context(name, value, attrs)
        context['widget'].update({
            'primary_subwidgets': [
                x for x in context['widget'].get('subwidgets', []) if
                x['attrs'].get('data-section') == 'primary'
            ],
            'additional_subwidgets': [
                x for x in context['widget'].get('subwidgets', []) if
                x['attrs'].get('data-section') == 'additional'
            ]
        })
        return context

    def decompress(self, value):
        if value:
            return [dict(value).get(x.get('value')) for x in self.choices]
        elif self.input_type == EventQuantityInput:
            return [0 for x in self.choices]
        return [None for x in self.choices]


class EventChoiceField(forms.MultiValueField):
    '''
    This field type handles the separate checkboxes or quantity inputs associated
    with each suboption (role or drop-in) for each event.
    '''

    def __init__(self, **kwargs):
        # Add field attributes for the associated event, and a dictionary of
        # additional field features (e.g. roles, drop-ins, etc.).
        self.event = kwargs.pop('event', None)
        self.field_type = kwargs.pop('field_type', forms.BooleanField)

        user = kwargs.pop('user', None)
        regClosed = kwargs.pop('regClosed', False)
        interval = kwargs.pop('interval', None)

        field_choices = []

        occurrence_filters = {}
        if interval:
            occurrence_filters.update({
                'endTime__gte': interval[0],
                'startTime__lte': interval[1]
            })

        can_override_capacity = user and user.has_perm('core.override_register_soldout')

        # Get the set of roles for registration.  If custom roles and capacities
        # are provided, those will be used.  Or, if the DanceType of a Series
        # provides default roles, those will be used.  Otherwise, a single role will
        # be defined as 'Register' .
        roles = self.event.availableRoles

        # Add one choice per role
        for role in roles:
            this_choice = {
                'value': 'role_%s' % role.id,
                'data-section': 'primary',
                'data-type': 'role',
                'data-role-name': role.name,
                'data-role-plural-name': role.pluralName,
                'data-num-registered': self.event.numRegisteredForRole(role),
                'data-capacity': self.event.capacityForRole(role),

                # This is popped and therefore not sent to client
                'data-capacity-override': can_override_capacity,
            }

            if self.event.soldOutForRole(role):
                this_choice.update({'data-sold-out': True, 'disabled': True})
                if can_override_capacity:
                    this_choice.update({'disabled': False, 'data-override': True})
                if regClosed:
                    this_choice.update({'data-closed': True, 'data-override': True})
            field_choices.append(this_choice)

        # If no choices, then add a general Register choice
        if not roles:
            this_choice = {
                'value': 'general',
                'data-section': 'primary',
                'data-type': 'general',
                'data-num-registered': self.event.numRegistered,
                'data-capacity': self.event.capacity,

                # This is popped and therefore not sent to client
                'data-capacity-override': can_override_capacity,
            }
            if self.event.soldOut:
                this_choice.update({'data-sold-out': True, 'disabled': True})
                if user and user.has_perm('core.override_register_soldout'):
                    this_choice.update({'disabled': False, 'data-override': True})
                if regClosed:
                    this_choice.update({'data-closed': True, 'data-override': True})
            field_choices.append(this_choice)

        # Add drop-in choices if they are available and if this user has permission.
        # If the user only has override permissions, add the override collapse only.
        # Note that this works because django-polymorphic returns the subclass.
        if isinstance(self.event, Series) and (
            (self.event.allowDropins and user and user.has_perm('core.register_dropins')) or
            (user and user.has_perm('core.override_register_dropins'))
        ):
            for occurrence in self.event.eventoccurrence_set.filter(**occurrence_filters):
                this_choice = {
                    'value': 'dropin_%s' % occurrence.id,
                    'data-section': 'additional',
                    'data-type': 'dropIn',
                    'data-occurrence': occurrence.id,
                    'data-occurrence-start-time': ensure_localtime(occurrence.startTime),
                    'data-num-registered': self.event.numRegistered,
                    'data-capacity': self.event.capacity,

                    # This is popped and therefore not sent to client
                    'data-capacity-override': can_override_capacity,
                }
                if (user and user.has_perm('core.override_register_dropins')):
                    this_choice['data-override'] = True
                field_choices.append(this_choice)

        error_messages = {
            'incomplete': _('Invalid selection for event.'),
        }
        fields = [self.field_type(required=False) for x in field_choices]
        widget = EventChoiceMultiWidget(
            choices=field_choices, field_type=self.field_type
        )
        self.field_choices = field_choices

        super().__init__(
            error_messages=error_messages, fields=fields,
            require_all_fields=False, widget=widget, **kwargs
        )

    def compress(self, data_list):
        compressed = [
            (self.field_choices[i].get('value','register'), int(data_list[i] or 0))
            for i in range(len(data_list))
        ]
        return compressed

