from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import (
    Q, F, Count, Case, When, ExpressionWrapper, BooleanField, IntegerField
)
from django.forms.widgets import mark_safe
from django.utils.translation import gettext_lazy as _, gettext

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML, Submit
import logging

from ..models import Event, Customer
from ..constants import HOW_HEARD_CHOICES, getConstant, REG_VALIDATION_STR
from ..signals import check_student_info, collect_student_info_fields
from ..utils.timezone import ensure_localtime


# Define logger for this file
logger = logging.getLogger(__name__)


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

        # We only want validation messages to show up once, so pop messages that
        # have already show up before checking to see if any messages remain to
        # be shown. Use the message tags to identify messages that have already
        # appeared.
        prior_messages = self._session.pop('prior_messages', [])
        remaining_messages = []

        for m in msgs:
            m_dict = {'level': m.level, 'extra_tags': m.extra_tags}
            if (
                (m_dict not in prior_messages) or
                ('prevent_registration' in m_dict['extra_tags'])
            ):
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
        required=False,
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

        extra = getattr(self, '_extra_mid_layout', [])
        mid_layout = Layout(
            Div(*fields, *extra, css_class='card card-body bg-light my-2'),
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
        self._add_more_url = kwargs.pop('add_more_url', None)
        super().__init__(*args, **kwargs)

        user = getattr(self._request, 'user', None)
        session = self._session

        # Input existing info for users who are logged in and have signed up before
        if user and hasattr(user, 'customer') and user.customer and not session.get('payAtDoor', False):
            self.fields['firstName'].initial = user.customer.first_name or user.first_name
            self.fields['lastName'].initial = user.customer.last_name or user.last_name
            self.fields['email'].initial = user.customer.email or user.email
            self.fields['phone'].initial = user.customer.phone

        self.fields['student'].label = _('I am a {label}'.format(label=getConstant('registration__studentFieldLabel')))

        # Let other apps inject extra fields into the mid-section of the form.
        # Each handler returns None or a list of (field_name, field, layout_element).
        self._extra_mid_layout = []
        eventRegs = (
            self._registration.eventregistration_set.all()
            if self._registration else []
        )
        for _handler, result in collect_student_info_fields.send(
            sender=RegistrationContactForm,
            instance=self,
            registration=self._registration,
            invoice=self._invoice,
            request=self._request,
            eventRegs=eventRegs,
        ):
            if result:
                for field_name, field, layout_element in result:
                    self.fields[field_name] = field
                    self._extra_mid_layout.append(layout_element)

        buttons = [Submit('submit', _('Proceed with Registration'))]
        if self._add_more_url:
            buttons.append(HTML(
                '<a href="%s" class="btn btn-outline-secondary mr-2">%s</a>' % (
                    self._add_more_url, gettext('Add more items')
                )
            ))
        self.helper.layout = Layout(
            self.get_top_layout(),
            self.get_mid_layout(),
            self.get_bottom_layout(),
            *buttons,
        )

        # If a voucher ID was passed (i.e. a referral code), then populate the form
        # and clear the passed session value
        if session.get('voucher_id') and self.fields.get('gift', None):
            self.fields['gift'].initial = session.get('voucher_id')
            self.fields['gift'].widget.attrs['readonly'] = True
            session.pop('voucher_id', None)
            session.pop('voucher_names', None)
            session.pop('total_voucher_amount', None)
        # If a voucher code was submitted via the cart (new CartView path), pre-fill
        # the gift field so StudentInfoView can preview and validate it.
        elif (
            self._invoice and
            self._invoice.data.get('discount_code') and
            self.fields.get('gift', None)
        ):
            self.fields['gift'].initial = self._invoice.data.get('discount_code')

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

        # Make this an attribute of the class instance so that we can use the
        # same queryset in form validation.
        self.event_regs = self._registration.eventregistration_set.select_related(
            'invoiceItem', 'customer', 'event', 'role'
        ).annotate(
            child=ExpressionWrapper(
                Q(invoiceItem__parent_item__isnull=False),
                output_field=BooleanField()
            ),
            base_id=Case(
                When(
                    invoiceItem__parent_item__eventRegistration__isnull=False,
                    then=F('invoiceItem__parent_item__eventRegistration__id')
                ),
                default=F('id'),
                output_field=IntegerField(),
            ),
            firstName=F('customer__first_name'),
            lastName=F('customer__last_name'),
            email=F('customer__email'),
        ).order_by('base_id', 'child', 'event__startTime', 'event__id', 'id')

        prior_event_ids = []

        for er in self.event_regs:
            first_of_event = (er.event.id not in prior_event_ids) and not er.child
            prior_event_ids.append(er.event.id)

            this_event_details = er.event.get_real_instance().name
            if er.role:
                this_event_details += ' - %s' % er.role.name
            if er.dropIn:
                this_event_details += ' - %s' % _('Drop-in')

            this_event_date = _(
                'Begins %s' % (ensure_localtime(er.event.startTime).strftime('%a., %B %d, %Y, %I:%M %p'))
            )

            if not er.child:
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

                if getConstant('registration__addStudentField') and not er.child:
                    self.fields['er_%s_student' % er.id] = forms.BooleanField(
                        label=getConstant('registration__studentFieldLabel'),
                        required=False, initial=er.student
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
        for er in self.event_regs:            
            names[er.id] = {
                'firstName': self.cleaned_data.get('er_%s_firstName' % er.base_id),
                'lastName': self.cleaned_data.get('er_%s_lastName' % er.base_id),
                'email': self.cleaned_data.get('er_%s_email' % er.base_id),
            }

        for er in self.event_regs:
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

        # We didn't create name information fields for the child eventregistrations
        # so now we add them to the cleaned data as if the person filled in the
        # same name for all child registrations as for the parent.
        for er in self.event_regs.filter(child=True):
            self.cleaned_data.update({
                'er_%s_firstName' % er.id: self.cleaned_data.get('er_%s_firstName' % er.base_id),
                'er_%s_lastName' % er.id: self.cleaned_data.get('er_%s_lastName' % er.base_id),
                'er_%s_email' % er.id: self.cleaned_data.get('er_%s_email' % er.base_id),
                'er_%s_phone' % er.id: self.cleaned_data.get('er_%s_phone' % er.base_id, None),
                'er_%s_student' % er.id: self.cleaned_data.get('er_%s_studetn' % er.base_id, False),
            })

        return self.cleaned_data
