from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _

from dal import autocomplete
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML, Hidden, Submit
from dal import autocomplete
from random import random
import json
import logging

from danceschool.core.models import Invoice, TemporaryRegistration, Event
from .models import PayAtDoorFormModel


class CashPaymentMixin(object):
    '''
    This mixin provides methods for cleaning fields that are used in all
    cash payment forms.
    '''

    def clean_submissionUser(self):
        user_id = self.data.get('submissionUser') or None

        if user_id is 'None' or not user_id:
            return None

        user = User.objects.get(id=user_id)

        if not user:
            raise ValidationError(_('submissionUser not found.'))
        return user

    def clean_invoice(self):
        invoice_id = self.data.get('invoice') or None

        if invoice_id:
            invoice = Invoice.objects.get(id=invoice_id)
        if not invoice_id or not invoice:
            raise ValidationError(_('Invoice not found.'))
        return invoice


class WillPayAtDoorForm(forms.Form):
    ''' 
    This is the form that customers fill out indicating
    that they intend to provide a cash payment at-the-door.
    When this form is submitted, the registration is allowed
    to proceed, but the invoice is not yet marked as paid.
    '''
    registration = forms.ModelChoiceField(queryset=TemporaryRegistration.objects.all(),required=True)
    submissionUser = forms.ModelChoiceField(queryset=User.objects.all(),required=False)
    instance = forms.ModelChoiceField(queryset=PayAtDoorFormModel.objects.all(),required=True)

    willPayAtDoor = forms.BooleanField(
        label=_('I will pay at the door'),
        required=True,
        help_text=_('You will receive a registration confirmation email, but will be required to complete your payment at the door to finalize your registration.')
    )

    def __init__(self,*args,**kwargs):
        subUser = kwargs.pop('user','')
        instance = kwargs.pop('instance',None)
        registration = kwargs.pop('registration',None)

        # Invoice is not used for this form, but pop it out of kwargs to avoid issues.
        kwargs.pop('invoice',None)

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = False  # Our template must explicitly include the <form tag>
        self.helper.form_action = reverse('doorWillPayHandler')

        subUser_layout = Layout(Hidden('submissionUser',subUser)) if subUser else Layout()

        self.helper.layout = Layout(
            HTML("""
                <div class="card mt-4">
                    <h6 class="card-header" role="tab" id="door_headingOne">
                        """ + str(_('Pay at the door')) + """
                    </h6>
                    <div class="card-body">
                """),
            Hidden('registration',registration),
            subUser_layout,
            Hidden('instance', instance),
            'willPayAtDoor',
            Submit('submit',_('Submit')),
            HTML("""
                    </div>
                </div>
            """),
        )

        super(WillPayAtDoorForm,self).__init__(*args, **kwargs)


class DoorPaymentForm(CashPaymentMixin, forms.Form):
    '''
    This is the form that staff users fill out to indicate
    that they received a cash payment at-the-door.
    '''

    submissionUser = forms.ModelChoiceField(queryset=User.objects.filter(Q(staffmember__isnull=False) | Q(is_staff=True)),required=True)
    invoice = forms.ModelChoiceField(queryset=Invoice.objects.all(),required=True)
    instance = forms.ModelChoiceField(queryset=PayAtDoorFormModel.objects.all(),required=True)

    receivedBy = forms.ModelChoiceField(
        queryset=User.objects.filter(Q(staffmember__isnull=False) | Q(is_staff=True)),
        label=_('Payment received by:'),
        required=True,
        widget=autocomplete.ModelSelect2(
            url='autocompleteUser',
            attrs={
                # This will set the input placeholder attribute:
                'data-placeholder': _('Enter a user name'),
                # This will set the yourlabs.Autocomplete.minimumCharacters
                # options, the naming conversion is handled by jQuery
                'data-autocomplete-minimum-characters': 2,
                'data-widget-maximum-values': 4,
                'class': 'modern-style',
            }
        )
    )
    amountPaid = forms.FloatField(label=_('Amount Paid'),required=True,min_value=0)

    def __init__(self,*args,**kwargs):
        subUser = kwargs.pop('user','')
        instance = kwargs.pop('instance',None)
        invoiceId = kwargs.pop('invoice',None)

        # Registration is not used for this form, but pop it out of kwargs to avoid issues.
        kwargs.pop('registration',None)

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = False  # Our template must explicitly include the <form tag>
        self.helper.form_action = reverse('doorPaymentHandler')

        self.helper.layout = Layout(
            HTML("""
                <div class="card mt-4">
                    <h6 class="card-header" role="tab" id="door_headingOne">
                        """ + str(_('Cash Payment')) + """
                    </h6>
                    <div class="card-body">
                """),
            Hidden('submissionUser',subUser),
            Hidden('instance',instance),
            Hidden('invoice',invoiceId),
            'receivedBy',
            'amountPaid',
            Submit('submit',_('Submit')),
            HTML("""
                    </div>
                </div>
            """),
        )

        kwargs.update(initial={
            'receivedBy': subUser,
        })

        super(DoorPaymentForm,self).__init__(*args, **kwargs)

    def clean_submissionUser(self):
        user = super(DoorPaymentForm,self).clean_submissionUser()

        if not user.has_perm('core.accept_door_payments'):
            raise ValidationError(_('Invalid user submitted door payment.'))
        return user
