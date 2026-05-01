from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, HTML, Hidden, Submit
import logging

from ..models import Invoice

# Define logger for this file
logger = logging.getLogger(__name__)


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
