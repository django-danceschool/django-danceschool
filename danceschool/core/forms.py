from django import forms
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q, F, Count
from django.utils.encoding import force_str
from django.forms.widgets import mark_safe, Select
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _, gettext

from itertools import chain
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML, Hidden, Submit
from dal import autocomplete
from random import random
import json
import logging
from djangocms_text_ckeditor.widgets import TextEditorWidget

from .models import (
    EventStaffMember, SubstituteTeacher, Event, EventOccurrence,
    Series, SeriesTeacher, Instructor, StaffMember, EmailTemplate, Location,
    Customer, Invoice, get_defaultEmailName, get_defaultEmailFrom
)
from .constants import HOW_HEARD_CHOICES, getConstant, REG_VALIDATION_STR
from .signals import check_student_info
from .utils.emails import get_text_for_html
from .utils.timezone import ensure_localtime


# Define logger for this file
logger = logging.getLogger(__name__)


class LocationWithDataWidget(Select):
    '''
    Override render_option to permit extra data of default capacity
    and room options to be used by JQuery.
    '''

    def render_option(self, selected_choices, option_value, option_label):
        if option_value is None:
            option_value = ''
        option_value = force_str(option_value)
        if option_value in selected_choices:
            selected_html = mark_safe(' selected="selected"')
            if not self.allow_multiple_selected:
                # Only allow for a single selection.
                selected_choices.remove(option_value)
        else:
            selected_html = ''

        # Pass the default location capacity as an option
        if option_value:
            this_location = Location.objects.filter(id=int(option_value)).first()
            defaultCapacity = this_location.defaultCapacity
            room_options = [
                {'id': x.id, 'name': x.name, 'defaultCapacity': x.defaultCapacity}
                for x in this_location.room_set.all()
            ]

            extra_value_data = format_html(
                ' data-defaultCapacity="{}" data-roomOptions="{}"',
                defaultCapacity, json.dumps(room_options))
        else:
            extra_value_data = ''

        return format_html('<option value="{}"{}{}>{}</option>',
                           option_value,
                           mark_safe(selected_html),
                           extra_value_data,
                           force_str(option_label))


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


class ClassChoiceForm(forms.Form):
    '''
    This is the form that customers use to select classes.
    '''

    def __init__(self, *args, **kwargs):
        openEvents = kwargs.pop('openEvents', Event.objects.none())
        closedEvents = kwargs.pop('closedEvents', Event.objects.none())
        user = kwargs.pop('user', None)
        interval = kwargs.pop('interval', None)
        voucherField = kwargs.pop('voucherField', False)

        # Only the keys passed in this property will be entered into session data.
        # This prevents injection of unknown values into the registration process.
        self.permitted_event_keys = kwargs.pop('permittedEventKeys', ['role', ])

        # Initialize a default (empty) form to fill
        super().__init__(*args, **kwargs)

        # Allow users with appropriate permissions to process door registrations.
        if user and user.has_perm('core.accept_door_payments'):
            self.fields['payAtDoor'] = forms.BooleanField(
                required=False, label=_('Door/Invoice Registration')
            )

        # If specified in form kwargs, add a voucher code field.
        if voucherField:
            self.fields['gift'] = forms.CharField(required=False, label=_('Voucher ID'))

        if user and user.has_perm('core.override_register_closed'):
            choice_set = openEvents | closedEvents
        else:
            choice_set = openEvents

        field_type_rule = getConstant('registration__widgetType')

        for event in choice_set:
            event_field_type = forms.IntegerField
            if (
                field_type_rule == 'AC' or
                (field_type_rule == 'SC' and event.polymorphic_ctype.model == 'series') or
                (field_type_rule == 'SQ' and event.polymorphic_ctype.model != 'series')
            ):
                event_field_type = forms.BooleanField

            self.fields[event.polymorphic_ctype.model + '_' + str(event.id)] = EventChoiceField(
                event=event, label=event.name, required=False, user=user,
                regClosed=(event in closedEvents), interval=interval,
                field_type=event_field_type
            )

    def clean(self):
        '''
        Check that the registration is not empty and that restrictions on
        duplicate choices are not being violated.
        '''
        cleaned_data = super().clean()
        hasContent = False

        payAtDoor = cleaned_data.get('payAtDoor', False)

        for key, value in cleaned_data.items():
            if key.split('_')[0] in ['event', 'series', 'publicevent', 'privatelessonevent']:
                reg_list = []
                dropin_list = []

                for v in value:
                    if v[0].startswith('dropin_'):
                        dropin_list += [v[0] for i in range(v[1])]
                    else:
                        reg_list += [v[0] for i in range(v[1])]

                if reg_list or dropin_list:
                    hasContent = True

                if (
                    len(reg_list) > 1 and ((
                        'series_' in key and (
                            (getConstant('registration__multiRegSeriesRule') == 'N') or
                            (getConstant('registration__multiRegSeriesRule') == 'D' and not payAtDoor)
                        )) or (
                        'publicevent_' in key and (
                            (getConstant('registration__multiRegPublicEventRule') == 'N') or
                            (getConstant('registration__multiRegPublicEventRule') == 'D' and not payAtDoor)
                        ))
                    ) and (
                        getConstant('registration__multiRegNameFormRule') == 'N' or
                        (getConstant('registration__multiRegNameFormRule') == 'O' and payAtDoor)
                    )
                ):
                    raise ValidationError(_('Must select only one role.'), code='invalid')
                elif len(reg_list) >= 1 and len(dropin_list) > 0 and (
                    getConstant('registration__multiRegNameFormRule') == 'N' or
                    (getConstant('registration__multiRegNameFormRule') == 'O' and payAtDoor)
                ):
                    raise ValidationError(_(
                        'Cannot register for drop-in classes and also for the entire series.'
                    ), code='invalid')
        if not hasContent:
            raise ValidationError(_('Must register for at least one class or series.'))

    class Media:
        js = ('js/registration_number_input.js',)


class PartnerRequiredForm(forms.Form):
    '''
    When one or more events in a customer's registration have a partner
    required, this page is used to collect partner name information for each
    registrant to that event.
    '''

    def __init__(self, *args, **kwargs):
        self._parterRequiredRegs = kwargs.pop('partnerRequiredRegs', False)
        super().__init__(*args, **kwargs)

        # Setting use_custom_control to False to avoid issues with
        # django-crispy-forms Bootstrap integration.
        self.helper = FormHelper()
        self.helper.use_custom_control = False
        self.helper.form_method = 'post'
        self.helper.form_tag = False  # Our template must explicitly include the <form tag>

        # Hold information needed to lay out additional name fields
        reg_name_fields = []

        initial = self._parterRequiredRegs.annotate(
            firstName=F('customer__first_name'),
            lastName=F('customer__last_name'),
        ).order_by('event__startTime', 'event__id', 'id')

        for er in initial:
            this_event_details = er.event.get_real_instance().name
            if er.role:
                this_event_details += ' - %s' % er.role.name
            if er.dropIn:
                this_event_details += ' - %s' % _('Drop-in')

            this_event_date = _(
                'Begins %s' % (ensure_localtime(er.event.startTime).strftime('%a., %B %d, %Y, %I:%M %p'))
            )

            other_ers = initial.filter(
                event=er.event, dropIn=er.dropIn, customer__isnull=False
            ).exclude(customer=er.customer)
            field_names = []

            if other_ers:
                self.fields['er_%s_partner_customerId' % er.id] = forms.ChoiceField(
                    choices = (
                        [(x.customer.id, x.customer.fullName) for x in other_ers] +
                        [(0, _('Other')),]
                    ), label=_('Partner'), required=True, widget=forms.RadioSelect
                )
                field_names.append(('er_%s_partner_customerId' % er.id, _('Partner')))

            self.fields.update({
                'er_%s_partner_firstName' % er.id: forms.CharField(
                    label=False, required=False,
                ),
                'er_%s_partner_lastName' % er.id: forms.CharField(
                    label=False, required=False,
                ),
            })
            field_names += [
                ('er_%s_partner_firstName' % er.id, _('First Name')),
                ('er_%s_partner_lastName' % er.id, _('Last Name')),
            ]

            reg_name_fields.append({
                'event_details': this_event_details,
                'event_date': this_event_date,
                'field_names': field_names
            })       

        self.helper.layout = Layout(
            self.get_top_layout(),
            self.get_name_layout(reg_name_fields),
            Submit('submit', _('Complete Registration'), css_class='my-2')
        )

    def get_top_layout(self):
        pass

    def get_name_layout(self, reg_name_fields):
        '''
        Fields for additional names as needed when there are multiple
        EventRegistrations for the same event.
        '''
        rows = [
            Div(
                Div(
                    Div(
                        HTML('<strong>%s</strong>' % er_info.pop('event_details', '')),
                        HTML('<br /><small>%s</small>' % er_info.pop('event_date', '')),
                        css_class='col-lg'
                    ),
                    *[Field(x[0], placeholder=x[1], wrapper_class='col-lg') for x in er_info.get('field_names', [])],
                    css_class='form-row'
                ),
                css_class='list-group-item'
            ) for er_info in reg_name_fields
        ]

        return Layout(
            Div(
                Div(*rows, css_class='list-group'),
                css_class='card'
            )
        )

    def clean(self):
        '''
        Prevent the same partner from being listed for multiple event
        registrations.  If a customer ID is passed, then use the name information
        for that customer in place of whatever is in the name field.
        '''

        super().clean()

        partners = {}
        for er in self._parterRequiredRegs:
            if not partners.get(er.event, None):
                partners[er.event] = []

            this_partner = {
                'customerId': int(self.cleaned_data.get('er_%s_partner_customerId' % er.id, 0)),
                'firstName': self.cleaned_data.get('er_%s_partner_firstName' % er.id),
                'lastName': self.cleaned_data.get('er_%s_partner_lastName' % er.id),
            }

            if not this_partner['customerId'] and not this_partner['firstName']:
                self.add_error(
                    'er_%s_partner_firstName' % er.id,
                    _('This field is required.')
                )
            if not this_partner['customerId'] and not this_partner['lastName']:
                self.add_error(
                    'er_%s_partner_lastName' % er.id,
                    _('This field is required.')
                )
            if this_partner['customerId']:
                this_customer = Customer.objects.filter(
                    eventregistration__in=self._parterRequiredRegs,
                    id=this_partner['customerId']
                ).first()
                if not this_customer:
                    self.add_error(
                        'er_%s_partner_customerId' % er.id, _('Invalid customer')
                    )
                else:
                    self.cleaned_data['er_%s_partner_firstName' % er.id] = this_customer.first_name
                    self.cleaned_data['er_%s_partner_lastName' % er.id] = this_customer.last_name
                    this_partner['firstName'] = this_customer.first_name
                    this_partner['lastName'] = this_customer.last_name

            if this_partner in partners[er.event]:
                self.add_error('er_%s_partner_customerId' % er.id, _(
                    'The same person cannot be the partner for multiple ' +
                    'registrants. Please enter another name.'
                ))
            else:
                partners[er.event].append(this_partner)
 
        return self.cleaned_data

class RegistrationForm(forms.Form):
    '''
    A generic superclass that provides common methods for initialization and
    validation of forms within the registration process such as
    RegistrationContactForm and MultiRegCustomerNameForm.
    '''

    def __init__(self, *args, **kwargs):
        self._request = kwargs.pop('request', None)
        self._registration = kwargs.pop('registration', None)
        self._invoice = kwargs.pop('invoice', None)
        self._multireg = kwargs.pop('multiReg', False)
        session = getattr(self._request, 'session', {}).get(REG_VALIDATION_STR, {})

        super().__init__(*args, **kwargs)
        self._session = session

        # Setting use_custom_control to False to avoid issues with
        # django-crispy-forms Bootstrap integration.
        self.helper = FormHelper()
        self.helper.use_custom_control = False
        self.helper.form_method = 'post'
        self.helper.form_tag = False  # Our template must explicitly include the <form tag>

    def is_valid(self):
        '''
        For this form to be considered valid, there must be not only no errors,
        but also no messages on the request that need to be shown.
        '''

        valid = super().is_valid()
        msgs = messages.get_messages(self._request)

        # We only want validation messages to show up once, so pop messages that have already show up
        # before checking to see if any messages remain to be shown.
        prior_messages = self._session.pop('prior_messages', [])
        remaining_messages = []

        for m in msgs:
            m_dict = {'message': m.message, 'level': m.level, 'extra_tags': m.extra_tags}
            if m_dict not in prior_messages:
                remaining_messages.append(m_dict)

        if remaining_messages:
            self._session['prior_messages'] = remaining_messages
            self._request.session.modified = True
            return False
        return valid

    def check_customer(self, firstName, lastName, email, eventRegs=None):
        '''
        This method checks whether a customer has already signed up for an
        event, and is therefore ineligble to signup
        '''

        payAtDoor = self._session.get('payAtDoor', False)

        if not eventRegs:
            eventRegs = self._registration.eventregistration_set.all()

        eventRegs = eventRegs.values('event__id', 'dropIn').annotate(
            count=Count('event__id')
        ).order_by('event__id', 'dropIn')
        dropInRegs = eventRegs.filter(dropIn=True)
        seriesRegs = eventRegs.filter(dropIn=False, event__series__isnull=False)
        publicEventRegs = eventRegs.filter(dropIn=False, event__publicevent__isnull=False)

        # If the dynamic preference rules do not allow multiple registrations for
        # the same thing, then ensure that this customer is not already registered
        # for any of the Events in the list
        customer = Customer.objects.filter(
            first_name=firstName,
            last_name=lastName,
            email=email
        ).first()

        # Compile a list of Events for which the customer has already registered
        # that are not eligible for multiple registrations.  The logic also allows
        # registration for a full series after registering for a drop-in, but
        # not the other way around.
        already_registered_list = []
        duplicate_name_list = []

        if seriesRegs and (
            (getConstant('registration__multiRegSeriesRule') == 'N') or
            (getConstant('registration__multiRegSeriesRule') == 'D' and not payAtDoor)
        ):
            if customer:
                already_registered_list += list(customer.getSeriesRegistered(
                    eventregistration__dropIn=False, eventregistration__cancelled=False
                ).filter(
                    id__in=seriesRegs.values_list('event__id', flat=True)
                ))
            duplicate_name_list += list(seriesRegs.filter(count__gt=1))

        if publicEventRegs and (
            (getConstant('registration__multiRegPublicEventRule') == 'N') or
            (getConstant('registration__multiRegPublicEventRule') == 'D' and not payAtDoor)
        ):
            if customer:
                already_registered_list += list(customer.getSeriesRegistered(
                    eventregistration__dropIn=False, eventregistration__cancelled=False
                ).filter(
                    id__in=publicEventRegs.values_list('event__id', flat=True)
                ))
            duplicate_name_list += list(publicEventRegs.filter(count__gt=1))

        if dropInRegs and (
            (getConstant('registration__multiRegDropInRule') == 'N') or
            (getConstant('registration__multiRegDropInRule') == 'D' and not payAtDoor)
        ):
            if customer:
                already_registered_list += list(customer.getSeriesRegistered(
                    eventregistration__cancelled=False
                ).filter(
                    id__in=dropInRegs.values_list('event__id', flat=True)
                ))
            duplicate_name_list += list(dropInRegs.filter(count__gt=1))
        elif dropInRegs:
            if customer:
                already_registered_list += list(customer.getSeriesRegistered(
                    eventregistration__dropIn=False, eventregistration__cancelled=False
                ).filter(
                    id__in=dropInRegs.values_list('event__id', flat=True)
                ))
            duplicate_name_list += list(dropInRegs.filter(count__gt=1))

        if already_registered_list:
            error_list = '\n'.join(['<li>%s</li>' % (x.name,) for x in already_registered_list])
            raise ValidationError(gettext(mark_safe(
                'You are already registered for:\n<ul>\n%s\n</ul>' % error_list +
                '\nIf you are registering another person, please enter their name.'
            )))
        if duplicate_name_list:
            # Get the actual events again in order to get the event names.
            duplicate_name_events = Event.objects.filter(
                id__in=[x.get('event__id') for x in duplicate_name_list]
            )
            error_list = '\n'.join(['<li>%s</li>' % (x.name,) for x in duplicate_name_events])
            raise ValidationError(gettext(mark_safe(
                'You have entered the same name repeatedly for:\n<ul>\n%s\n</ul>' % error_list +
                '\nIf you are registering another person, please enter their name.'
            )))


class RegistrationContactForm(RegistrationForm):
    '''
    This is the form customers use to fill out their contact info.
    '''

    firstName = forms.CharField(label=_('First Name'))
    lastName = forms.CharField(label=_('Last Name'))
    email = forms.EmailField()
    phone = forms.CharField(
        required=False, label=_('Telephone (optional)'),
        help_text=_('We may use this to notify you in event of a cancellation.')
    )
    student = forms.BooleanField(
        required=False, label=_('I am a student'),
        help_text=_('Photo ID is required at the door')
    )
    agreeToPolicies = forms.BooleanField(
        required=True,
        label=_('<strong>I agree to all policies (required)</strong>'),
        help_text=_('By checking, you agree to abide by all policies.')
    )
    gift = forms.CharField(required=False, label=_('Voucher ID'))
    howHeardAboutUs = forms.ChoiceField(
        choices=HOW_HEARD_CHOICES, required=False,
        label=_('How did you hear about us?'), help_text=_('Optional')
    )
    comments = forms.CharField(
        widget=forms.Textarea, required=False, label=_('Comments'),
        help_text=_('Add anything else you\'d like to tell us.')
    )

    def get_top_layout(self):

        top_layout = Layout(
            Div(
                Field('firstName', wrapper_class='col'),
                Field('lastName', wrapper_class='col'),
                css_class='row'
            ),
            Div(
                Field('email', wrapper_class='col'),
                Field('phone', wrapper_class='col'),
                css_class='row'
            ),
        )
        return top_layout

    def get_mid_layout(self):
        fields = ['agreeToPolicies',]
        if getConstant('registration__addStudentField'):
            fields += ['student',]

        mid_layout = Layout(
            Div(*fields, css_class='card card-body bg-light my-2'),
        )
        return mid_layout

    def get_bottom_layout(self):
        bottom_layout = Layout(
            Div(
                Field('gift', wrapper_class='col'),
                Field('howHeardAboutUs', wrapper_class='col'),
                css_class='row mt-4'
            ),
            'comments',
        )
        return bottom_layout

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        user = getattr(self._request, 'user', None)
        session = self._session

        # Input existing info for users who are logged in and have signed up before
        if user and hasattr(user, 'customer') and user.customer and not session.get('payAtDoor', False):
            self.fields['firstName'].initial = user.customer.first_name or user.first_name
            self.fields['lastName'].initial = user.customer.last_name or user.last_name
            self.fields['email'].initial = user.customer.email or user.email
            self.fields['phone'].initial = user.customer.phone

        self.helper.layout = Layout(
            self.get_top_layout(),
            self.get_mid_layout(),
            self.get_bottom_layout(),
            Submit('submit', _('Proceed with Registration'))
        )

        # If a voucher ID was passed (i.e. a referral code), then populate the form
        # and clear the passed session value
        if session.get('voucher_id') and self.fields.get('gift', None):
            self.fields['gift'].initial = session.get('voucher_id')
            self.fields['gift'].widget.attrs['readonly'] = True
            session.pop('voucher_id', None)
            session.pop('voucher_names', None)
            session.pop('total_voucher_amount', None)

        # Pass along whether the individual is a student if this has already
        # been set in the session data.
        if session.get('student', None) is not None and self.fields.get('student', None):
            self.fields['student'].initial = session.get('student')

    def clean(self):
        # If this Invoice does not include multiple event registrations, then
        # we can go ahead and verify that they are not violating any of the
        # rules on when someone can register for the same event using the same
        # name.  This is done using the check_customer method.
        super().clean()

        eventRegs = []

        if not self._multireg:
            self.check_customer(
                self.cleaned_data.get('firstName'),
                self.cleaned_data.get('lastName'),
                self.cleaned_data.get('email')
            )
            if self._registration:
                eventRegs = self._registration.eventregistration_set.all()

        # Allow other handlers to add validation errors to the form.  Also, by
        # passing the request, we allow those handlers to add messages to the
        # request, which (for this form) are treated like errors in that
        # they prevent the form from being considered valid.
        check_student_info.send(
            sender=RegistrationContactForm,
            instance=self, data=self.cleaned_data,
            request=self._request,
            registration=self._registration,
            invoice=self._invoice,
            eventRegs=eventRegs,
        )

        return self.cleaned_data


class MultiRegCustomerNameForm(RegistrationForm):
    '''
    When a customer signs up for multiple EventRegistrations, we ensure
    that we have the correct customer for each.  This form is dynamically
    generated to provide the forms needed to validate customer information for
    each EventRegistration.
    '''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Hold information needed to lay out additional name fields
        reg_name_fields = []

        initial = self._registration.eventregistration_set.select_related(
            'customer', 'event', 'role'
        ).annotate(
            firstName=F('customer__first_name'),
            lastName=F('customer__last_name'),
            email=F('customer__email'),
        ).order_by('event__startTime', 'event__id', 'id')

        last_event_id = None
        for er in initial:
            first_of_event = (er.event.id != last_event_id)
            last_event_id = er.event.id

            this_event_details = er.event.get_real_instance().name
            if er.role:
                this_event_details += ' - %s' % er.role.name
            if er.dropIn:
                this_event_details += ' - %s' % _('Drop-in')

            this_event_date = _(
                'Begins %s' % (ensure_localtime(er.event.startTime).strftime('%a., %B %d, %Y, %I:%M %p'))
            )

            self.fields.update({
                'er_%s_isMe' % er.id: forms.BooleanField(
                    label=_('This is me'), required=False,
                    initial=first_of_event
                ),
                'er_%s_firstName' % er.id: forms.CharField(
                    label=False, required=True, initial=er.firstName
                ),
                'er_%s_lastName' % er.id: forms.CharField(
                    label=False, required=True, initial=er.lastName
                ),
                'er_%s_email' % er.id: forms.EmailField(
                    label=False, required=True, initial=er.email
                ),
            })

            field_names = [
                ('er_%s_isMe' % er.id, ''),
                ('er_%s_firstName' % er.id, _('First Name')),
                ('er_%s_lastName' % er.id, _('Last Name')),
                ('er_%s_email' % er.id, _('Email')),
            ]

            if getConstant('registration__addStudentField'):
                self.fields['er_%s_student' % er.id] = forms.BooleanField(
                    label=_('Student'), required=False, initial=er.student
                )
                field_names.append(('er_%s_student' % er.id, ''))

            reg_name_fields.append({
                'event_details': this_event_details,
                'event_date': this_event_date,
                'field_names': field_names,
            })       

        self.helper.layout = Layout(
            self.get_top_layout(),
            self.get_name_layout(reg_name_fields),
            Submit('submit', _('Complete Registration'), css_class='my-2')
        )

    def get_top_layout(self):
        pass

    def get_name_layout(self, reg_name_fields):
        '''
        Fields for additional names as needed when there are multiple
        EventRegistrations for the same event.
        '''
        rows = [
            Div(
                Div(
                    Div(
                        HTML('<strong>%s</strong>' % er_info.pop('event_details', '')),
                        HTML('<br /><small>%s</small>' % er_info.pop('event_date', '')),
                        css_class='col-lg'
                    ),
                    *[Field(x[0], placeholder=x[1], wrapper_class='col-lg') for x in er_info.get('field_names', [])],
                    css_class='form-row'
                ),
                css_class='list-group-item'
            ) for er_info in reg_name_fields
        ]

        return Layout(
            Div(
                Div(*rows, css_class='list-group'),
                css_class='card'
            )
        )

    def clean(self):
        super().clean()

        # First, populate a list of all names for each EventRegistration,
        # indexed by the ID of each EventRegistration.
        names = {}
        for er in self._registration.eventregistration_set.all():
            names[er.id] = {
                'firstName': self.cleaned_data.get('er_%s_firstName' % er.id),
                'lastName': self.cleaned_data.get('er_%s_lastName' % er.id),
                'email': self.cleaned_data.get('er_%s_email' % er.id),
            }

        for er in self._registration.eventregistration_set.all():
            this_name_ids = [k for k,x in names.items() if x == names[er.id]]

            self.check_customer(
                eventRegs=self._registration.eventregistration_set.filter(id__in=this_name_ids),
                **names[er.id],                    
            )

            # Allow other handlers to add validation errors to the form.  Also, by
            # passing the request, we allow those handlers to add messages to the
            # request, which (for this form) are treated like errors in that
            # they prevent the form from being considered valid.
            check_student_info.send(
                sender=MultiRegCustomerNameForm,
                instance=self, request=self._request,
                data=names[er.id],
                eventRegs=self._registration.eventregistration_set.filter(id__in=this_name_ids),
                registration=self._registration,
                invoice=self._invoice,
            )

        return self.cleaned_data


class CreateInvoiceForm(forms.Form):
    '''
    This form is used by staff users to create an invoice.
    '''

    submissionUser = forms.ModelChoiceField(
        queryset=User.objects.filter(Q(staffmember__isnull=False) | Q(is_staff=True)),
        required=True
    )
    invoiceSent = forms.BooleanField(label=_('Send Invoice'), required=True)
    invoicePayerEmail = forms.EmailField(label=_('Payer Email Address'), required=False)
    discountAmount = forms.FloatField(required=False)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        payerEmail = kwargs.pop('payerEmail', None)
        discountAmount = kwargs.pop('discountAmount', None)

        subUser = getattr(user, 'id', None)

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = False  # Our template must explicitly include the <form tag>

        self.helper.layout = Layout(
            HTML("""
                <div class="card mt-4">
                    <h6 class="card-header" role="tab" id="door_headingTwo">
                            """ + str(_('Send Invoice')) + """
                    </h6>
                    <div class="card-body">
                """),
            Hidden('submissionUser', subUser),
            'invoiceSent',
            'invoicePayerEmail',
            Hidden('discountAmount', discountAmount),
            Submit('submit', 'Submit'),
            HTML("""
                    </div>
                </div>
            """),
        )

        kwargs.update(initial={
            'invoicePayerEmail': payerEmail,
        })

        super().__init__(*args, **kwargs)

    def clean_submissionUser(self):
        invoiceSent = self.data.get('invoiceSent') or None
        user_id = self.data.get('submissionUser') or None

        if user_id:
            user = User.objects.get(id=user_id)
        if not user_id or not user:
            raise ValidationError(_('submissionUser not found.'))
        elif invoiceSent and not user.has_perm('core.send_invoices'):
            raise ValidationError(_('Invalid user submitted invoice.'))
        return user

    def clean(self):
        form_data = self.cleaned_data

        logger.debug('Form Data:\n%s' % form_data)

        invoiceSent = form_data.get('invoiceSent')

        if invoiceSent:
            if not form_data.get('submissionUser'):
                raise ValidationError(_('Submission user is required.'))
            if not form_data.get('invoicePayerEmail'):
                raise ValidationError(_('Must specify the email address of the invoice recipient.'))

        return form_data


class EventAutocompleteForm(forms.Form):
    '''
    This form can be used for views that autocomplete events (e.g. viewing
    registrations), but it has no other fields by default.
    '''

    event = forms.ModelChoiceField(
        queryset=Event.objects.filter(Q(publicevent__isnull=False) | Q(series__isnull=False)),
        label=_('Search for an Event'),
        required=True,
        widget=autocomplete.ModelSelect2(
            url='autocompleteEvent',
            attrs={
                # This will set the input placeholder attribute:
                'data-placeholder': _('Enter event title, year, or month'),
                # This will set the yourlabs.Autocomplete.minimumCharacters
                # options, the naming conversion is handled by jQuery
                'data-minimum-input-length': 0,
                'data-max-results': 10,
                'class': 'modern-style',
                'data-html': True,
            }
        )
    )

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.layout = Layout(
            'event',
            Submit('submit', _('Submit'))
        )


class RefundForm(forms.ModelForm):
    '''
    This is the form that is used to allocate refunds across series and events.
    If the Paypal app is installed, then it will also be used to submit refund
    requests to Paypal.  Note that most cleaning validation happens in Javascript.
    '''
    class Meta:
        model = Invoice
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        this_invoice = kwargs.pop('instance', None)

        for item in this_invoice.invoiceitem_set.all():
            initial = False
            if getattr(item, 'eventRegistration', None):
                initial = item.eventRegistration.cancelled
            item_max = item.total + item.taxes if this_invoice.buyerPaysSalesTax else item.total

            self.fields["item_cancelled_%s" % item.id] = forms.BooleanField(
                label=_('Cancelled'), required=False, initial=initial)
            self.fields['item_refundamount_%s' % item.id] = forms.FloatField(
                label=_('Refund Amount'), required=False,
                initial=(-1) * item.adjustments, min_value=0, max_value=item_max
            )

        self.fields['comments'] = forms.CharField(
            label=_('Explanation/Comments (optional)'), required=False,
            help_text=_(
                'This information will be added to the comments on the invoice ' +
                'associated with this refund.'
            ),
            widget=forms.Textarea(attrs={
                'placeholder': _('Enter explanation/comments...'),
                'class': 'form-control'
            })
        )

        self.fields['id'] = forms.ModelChoiceField(
            required=True, queryset=Invoice.objects.filter(id=this_invoice.id),
            widget=forms.HiddenInput(), initial=this_invoice.id
        )

        self.fields['initial_refund_amount'] = forms.FloatField(
            required=True, initial=(-1) * this_invoice.adjustments,
            min_value=0, max_value=this_invoice.amountPaid + this_invoice.refunds,
            widget=forms.HiddenInput()
        )

        self.fields['total_refund_amount'] = forms.FloatField(
            required=True, initial=0, min_value=0,
            max_value=this_invoice.amountPaid + this_invoice.refunds,
            widget=forms.HiddenInput()
        )

    def clean_total_refund_amount(self):
        '''
        The Javascript should ensure that the hidden input is updated, but double check it here.
        '''
        initial = self.cleaned_data.get('initial_refund_amount', 0)
        total = self.cleaned_data['total_refund_amount']
        summed_refunds = sum([
            v for k, v in self.cleaned_data.items() if k.startswith('item_refundamount_')
        ])

        if not self.cleaned_data.get('id'):
            raise ValidationError('ID not in cleaned data')

        if summed_refunds != total:
            raise ValidationError(_(
                'Passed value %s does not match sum of allocated refunds %s.' % (
                    total, summed_refunds
                )
            ))
        elif (
            summed_refunds > self.cleaned_data['id'].amountPaid +
            self.cleaned_data['id'].refunds
        ):
            raise ValidationError(_(
                'Total refunds allocated %s exceed revenue received %s.' % (
                    summed_refunds, self.cleaned_data['id'].amountPaid + self.cleaned_data['id'].refunds
                )
            ))
        elif total < initial:
            raise ValidationError(_('Cannot reduce the total amount of the refund.'))
        return total


class EmailContactForm(forms.Form):

    EMAIL_SENDTOSET_CHOICES = (
        ('series', _('All students in one or more series')),
        ('month', _('All Students in a given month'))
    )
    RICH_TEXT_CHOICES = (
        ('plain', _('Plain text email')),
        ('HTML', _('HTML rich text email'))
    )

    sendToSet = forms.ChoiceField(
        label=_('This email is for:'), widget=forms.RadioSelect,
        choices=EMAIL_SENDTOSET_CHOICES, required=False, initial='series'
    )

    template = forms.ModelChoiceField(
        label=_('(Optional) Select a template'), required=False,
        queryset=EmailTemplate.objects.none()
    )

    richTextChoice = forms.ChoiceField(
        label=_('Send this email as'), widget=forms.RadioSelect,
        choices=RICH_TEXT_CHOICES, required=True, initial='plain'
    )

    subject = forms.CharField(max_length=100)

    message = forms.CharField(widget=forms.Textarea, required=False)
    html_message = forms.CharField(widget=TextEditorWidget, required=False)

    from_name = forms.CharField(max_length=50, initial=get_defaultEmailName)
    from_address = forms.EmailField(max_length=100, initial=get_defaultEmailFrom)
    cc_myself = forms.BooleanField(label=_('CC Myself:'), initial=True, required=False)
    month = forms.ChoiceField(
        label=_('Email all students registered in month:'), initial='',
        required=False
    )
    series = forms.MultipleChoiceField(
        label=_('Email all students registered in a current/recent series:'),
        initial='', required=False
    )
    testemail = forms.BooleanField(
        label=_('Test email:'), help_text=_('Send a test email to myself only.'),
        initial=False, required=False
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        months = kwargs.pop('months', [])
        recentseries = kwargs.pop('recentseries', [])
        customers = kwargs.pop('customers', [])

        super().__init__(*args, **kwargs)

        if customers:
            self.fields['customers'] = forms.MultipleChoiceField(
                required=True,
                label=_('Selected customers'),
                widget=forms.CheckboxSelectMultiple(),
                choices=[(x.id, '%s <%s>' % (x.fullName, x.email)) for x in customers]
            )
            self.fields['customers'].initial = [x.id for x in customers]
            self.fields.pop('month', None)
            self.fields.pop('series', None)
            self.fields.pop('sendToSet', None)

            # Move the customer list to the top of the form
            self.fields.move_to_end('customers', last=False)

        else:
            self.fields['month'].choices = months
            self.fields['series'].choices = recentseries

        if user:
            self.fields['template'].queryset = EmailTemplate.objects.filter(
                Q(groupRequired__isnull=True) | Q(groupRequired__in=user.groups.all())
            ).filter(hideFromForm=False)

    def clean(self):
        # Custom cleaning ensures email is only sent to one of
        # a series, a month, or a set of customers
        super().clean()

        sendToSet = self.cleaned_data.get('sendToSet')
        customers = self.cleaned_data.get('customers')

        # We set to None and don't pop the keys out to prevent
        # KeyError issues with the subsequent view
        if sendToSet == 'series' or customers:
            self.cleaned_data['month'] = None
        if sendToSet == 'month' or customers:
            self.cleaned_data['series'] = None

        # If this is an HTML email, then ignore the plain text content
        # and replace it with plain text generated from the HTML.
        # If this is a plain text email, then ignore the HTML content.
        if self.cleaned_data['richTextChoice'] == 'HTML':
            if not self.cleaned_data['html_message']:
                raise ValidationError(_('Message is required.'))
            self.cleaned_data['message'] = get_text_for_html(self.cleaned_data['html_message'])
        if self.cleaned_data['richTextChoice'] == 'plain':
            if not self.cleaned_data['message']:
                raise ValidationError(_('Message is required.'))
            self.cleaned_data['html_message'] = None

        return self.cleaned_data

    class Media:
        js = ('js/emailcontact_sendToSet.js', 'js/emailcontact_ajax.js')


class SeriesTeacherChoiceField(forms.ModelChoiceField):
    '''
    This exists so that the validators for substitute teaching are not
    thrown off by the fact that the initial query is blank.
    '''

    def to_python(self, value):
        try:
            value = super().to_python(value)
        except (ValueError, ValidationError):
            key = self.to_field_name or 'pk'
            value = SeriesTeacher.objects.filter(**{key: value})
            if not value.exists():
                raise ValidationError(self.error_messages['invalid_choice'], code='invalid_choice')
            else:
                value = value.first()
        return value


class SeriesClassesChoiceField(forms.ModelMultipleChoiceField):
    '''
    This exists so that the validators for substitute teaching are not
    thrown off by the fact that the initial query is blank.
    '''

    def to_python(self, value):
        if not value:
            return []
        return list(self._check_values(value))

    def _check_values(self, value):
        """
        Given a list of possible PK values, returns a QuerySet of the
        corresponding objects. Raises a ValidationError if a given value is
        invalid (not a valid PK, not in the queryset, etc.)
        """
        key = self.to_field_name or 'pk'
        # deduplicate given values to avoid creating many querysets or
        # requiring the database backend deduplicate efficiently.
        try:
            value = frozenset(value)
        except TypeError:
            # list of lists isn't hashable, for example
            raise ValidationError(
                self.error_messages['list'],
                code='list',
            )
        for pk in value:
            try:
                self.queryset.filter(**{key: pk})
            except (ValueError, TypeError):
                raise ValidationError(
                    self.error_messages['invalid_pk_value'],
                    code='invalid_pk_value',
                    params={'pk': pk},
                )
        qs = EventOccurrence.objects.filter(**{'%s__in' % key: value})
        pks = set(force_str(getattr(o, key)) for o in qs)
        for val in value:
            if force_str(val) not in pks:
                raise ValidationError(
                    self.error_messages['invalid_choice'],
                    code='invalid_choice',
                    params={'value': val},
                )
        return qs


class SubstituteReportingForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)

        # Ensure 'initial' is initialized to avoid KeyError issues and fill in the Sub category
        kwargs['initial'] = kwargs.get('initial', {})
        kwargs['initial'].update(
            {'category': getConstant('general__eventStaffCategorySubstitute').id}
        )

        # If the user is a staffMember, then populate the form with their info
        if hasattr(user, 'staffmember'):
            kwargs['initial'].update({
                'staffMember': user.staffmember,
                'submissionUser': user,
            })

        super().__init__(*args, **kwargs)
        self.fields['event'] = forms.ModelChoiceField(queryset=Series.objects.order_by('-startTime'))
        self.fields['staffMember'] = forms.ModelChoiceField(queryset=StaffMember.objects.filter(
                instructor__isnull=False,
            ).exclude(
                instructor__status__in=[
                    Instructor.InstructorStatus.hidden,
                    Instructor.InstructorStatus.retired,
                    Instructor.InstructorStatus.retiredGuest
                ]
            ).order_by('instructor__status', 'lastName', 'firstName'))
        self.fields['replacedStaffMember'] = SeriesTeacherChoiceField(
            queryset=SeriesTeacher.objects.none()
        )
        self.fields['occurrences'] = SeriesClassesChoiceField(queryset=EventOccurrence.objects.none())
        self.fields['submissionUser'].widget = forms.HiddenInput()
        self.fields['category'].widget = forms.HiddenInput()

    def clean(self):
        '''
        This code prevents multiple individuals from substituting for the
        same class and class teacher.  It also prevents an individual from
        substituting for a class in which they are a teacher.
        '''
        super().clean()

        occurrences = self.cleaned_data.get('occurrences', [])
        staffMember = self.cleaned_data.get('staffMember')
        replacementFor = self.cleaned_data.get('replacedStaffMember', [])
        event = self.cleaned_data.get('event')

        for occ in occurrences:
            for this_sub in occ.eventstaffmember_set.all():
                if this_sub.replacedStaffMember == replacementFor:
                    self.add_error(
                        'occurrences',
                        ValidationError(_(
                            'One or more classes you have selected already ' +
                            'has a substitute teacher for that class.'
                        ), code='invalid')
                    )

        if event and staffMember:
            if staffMember in [
                x.staffMember for x in
                event.eventstaffmember_set.filter(
                    category__in=[
                        getConstant('general__eventStaffCategoryAssistant'),
                        getConstant('general__eventStaffCategoryInstructor')
                    ]
                )
            ]:
                self.add_error('event', ValidationError(_(
                    'You cannot substitute teach for a class in which you were an instructor.'
                ), code='invalid'))

    def validate_unique(self):
        '''
        We don't need to check the unique_together constraint in this form, because if the
        constraint is not satisfied, then the form will just update the existing instance
        in the save() method below.
        '''
        pass

    def save(self, commit=True):
        '''
        If a staff member is reporting substitute teaching for a second time, then we should update
        the list of occurrences for which they are a substitute on their existing EventStaffMember
        record, rather than creating a new record and creating database issues.
        '''
        existing_record = EventStaffMember.objects.filter(
            staffMember=self.cleaned_data.get('staffMember'),
            event=self.cleaned_data.get('event'),
            category=getConstant('general__eventStaffCategorySubstitute'),
            replacedStaffMember=self.cleaned_data.get('replacedStaffMember'),
        )
        if existing_record.exists():
            record = existing_record.first()
            for x in self.cleaned_data.get('occurrences'):
                record.occurrences.add(x)
            record.save()
            return record
        else:
            return super().save()

    class Meta:
        model = SubstituteTeacher
        exclude = ['data',]

    class Media:
        js = ('js/substituteteacher_ajax.js',)


class StaffMemberBioChangeForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        # Initialize a default form to fill
        super().__init__(*args, **kwargs)

        # If the individual is an instructor, then add the availableForPrivates field
        if getattr(self.instance, 'instructor', None):
            self.fields['availableForPrivates'] = forms.BooleanField(
                label=_('Available For private lessons'),
                initial=True,
                required=False,
                help_text=_(
                    'Check this box if you would like to be listed as ' +
                    'available for private lessons from students.'
                )
            )

    def save(self, commit=True):
        '''
        If the staff member is an instructor, also update the availableForPrivates
        field on the Instructor record.
        '''
        if getattr(self.instance, 'instructor', None):
            self.instance.instructor.availableForPrivates = self.cleaned_data.pop(
                'availableForPrivates', self.instance.instructor.availableForPrivates
            )
            self.instance.instructor.save(update_fields=['availableForPrivates', ])
        super().save(commit=True)

    class Meta:
        model = StaffMember
        fields = ['publicEmail', 'privateEmail', 'phone']


class RepeatEventForm(forms.Form):

    startDate = forms.DateField(label=_('First event occurs on'))
    repeatEvery = forms.IntegerField(label=_('Repeat every'), min_value=1, initial=1)
    periodicity = forms.ChoiceField(
        label=_('Period'),
        choices=(('D', _('Days')), ('W', _('Weeks')), ('M', _('Months')),),
        initial='W'
    )
    quantity = forms.IntegerField(
        label=_('Repeat this many times'), min_value=1, max_value=99, required=False
    )
    endDate = forms.DateField(label=_('Repeat until this date'), required=False)

    def clean(self):
        startDate = self.cleaned_data.get('startDate')
        endDate = self.cleaned_data.get('endDate')
        quantity = self.cleaned_data.get('quantity')

        if endDate and not endDate >= startDate:
            self.add_error('endDate', ValidationError(_('End date must be after start date.')))

        if quantity and endDate:
            self.add_error(
                'quantity', ValidationError(_(
                    'Please specify either a number of repeats or an end date, not both.'
                ))
            )


class InvoiceNotificationForm(forms.Form):
    '''
    This form just allows customers to deselect invoices for notification.
    '''

    def __init__(self, *args, **kwargs):
        invoices = kwargs.pop('invoices', Invoice.objects.none())

        # Initialize a default (empty) form to fill
        super().__init__(*args, **kwargs)

        for invoice in invoices:
            self.fields['invoice_%s' % invoice.id] = forms.BooleanField(
                label=invoice.id, required=False, initial=True
            )
