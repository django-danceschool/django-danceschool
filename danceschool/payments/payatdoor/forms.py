from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.urls import reverse
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from dal import autocomplete
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, HTML, Hidden, Submit
from dal import autocomplete

from danceschool.core.models import Invoice
from .models import PayAtDoorFormModel
from .constants import ATTHEDOOR_PAYMENTMETHOD_CHOICES


class CashPaymentMixin(object):
    '''
    This mixin provides methods for cleaning fields that are used in all
    cash payment forms.
    '''

    def clean_submissionUser(self):
        user_id = self.data.get('submissionUser') or None

        if user_id == 'None' or not user_id:
            return None

        user = User.objects.get(id=user_id)

        if not user:
            raise ValidationError(_('submissionUser not found.'))
        return user

    def clean_invoice(self):
        invoice_id = self.data.get('invoice') or None

        if invoice_id:
            try:
                invoice = Invoice.objects.get(id=invoice_id)
                return invoice
            except ObjectDoesNotExist:
                raise ValidationError(_('Invoice not found.'))


class WillPayAtDoorForm(forms.Form):
    '''
    This is the form that customers fill out indicating
    that they intend to provide a cash payment at-the-door.
    When this form is submitted, the registration is allowed
    to proceed, but the invoice is not yet marked as paid.
    '''
    invoice = forms.ModelChoiceField(queryset=Invoice.objects.all(), required=True)
    submissionUser = forms.ModelChoiceField(queryset=User.objects.all(), required=False)
    instance = forms.ModelChoiceField(queryset=PayAtDoorFormModel.objects.all(), required=True)

    willPayAtDoor = forms.BooleanField(
        label=_('I will pay at the door'),
        required=True,
        help_text=_(
            'You will receive a registration confirmation email, but will be ' +
            'required to complete your payment at the door to finalize your ' +
            'registration.'
        )
    )

    def __init__(self, *args, **kwargs):
        subUser = kwargs.pop('user', '')
        instance = kwargs.pop('instance', None)
        invoiceId = kwargs.pop('invoice', None)

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = False  # Our template must explicitly include the <form tag>
        self.helper.form_action = reverse('doorWillPayHandler')

        subUser_layout = Layout(Hidden('submissionUser', subUser)) if subUser else Layout()

        self.helper.layout = Layout(
            HTML("""
                <div class="card mt-4">
                    <h6 class="card-header" role="tab" id="door_headingOne">
                        """ + str(_('Pay at the door')) + """
                    </h6>
                    <div class="card-body">
                """),
            Hidden('invoice', invoiceId),
            subUser_layout,
            Hidden('instance', instance),
            'willPayAtDoor',
            Submit('submit', _('Submit')),
            HTML("""
                    </div>
                </div>
            """),
        )

        super().__init__(*args, **kwargs)


class DoorPaymentForm(CashPaymentMixin, forms.Form):
    '''
    This is the form that staff users fill out to indicate
    that they received a cash payment at-the-door.
    '''

    submissionUser = forms.ModelChoiceField(
        queryset=User.objects.filter(Q(staffmember__isnull=False) | Q(is_staff=True)),
        required=True
    )
    invoice = forms.ModelChoiceField(queryset=Invoice.objects.all(), required=True)

    amountPaid = forms.FloatField(label=_('Amount Paid'), required=True, min_value=0)
    paymentMethod = forms.ChoiceField(
        label=_('Payment method'),
        required=True,
        initial='Cash',
        choices=ATTHEDOOR_PAYMENTMETHOD_CHOICES,
    )

    payerEmail = forms.EmailField(label=_('Payer Email Address'), required=False)
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

    def __init__(self, *args, **kwargs):
        subUser = kwargs.pop('user', '')
        invoiceId = kwargs.pop('invoice', None)
        initialAmount = kwargs.pop('initialAmount', None)

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = False  # Our template must explicitly include the <form tag>
        self.helper.form_action = reverse('doorPaymentHandler')

        self.helper.layout = Layout(
            Hidden('submissionUser', subUser),
            Hidden('invoice', invoiceId),
            'amountPaid',
            'paymentMethod',
            'payerEmail',
            'receivedBy',
            Submit('submit', _('Submit')),
        )

        kwargs.update(initial={
            'receivedBy': subUser,
            'amountPaid': initialAmount
        })

        super().__init__(*args, **kwargs)

    def clean_submissionUser(self):
        user = super().clean_submissionUser()

        if not user.has_perm('core.accept_door_payments'):
            raise ValidationError(_('Invalid user submitted door payment.'))
        return user
