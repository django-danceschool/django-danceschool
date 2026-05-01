from django import forms
from django.utils.translation import gettext_lazy as _

from danceschool.core.forms.event import EventAutocompleteForm
from .models import SquarePaymentRecord


class CreateInvoiceForm(EventAutocompleteForm):

    comments=forms.CharField(
        label=_('Optional comments'), required=False, widget=forms.Textarea()
    )

    def __init__(self, *args, **kwargs):
        ''' Make event field optional and change the label. '''
        super().__init__(*args, **kwargs)
        self.fields['event'].required = False
        self.fields['event'].label = _(
            'Optionally, associate this payment to an event.'
        )
        self.fields['event'].help_text = _('''
            If you do not specify an event, then the invoice will be created
            as of the date the payment was received, but it will not be linked
            to any particular event.
        ''')

    class Meta:
        model = SquarePaymentRecord
        fields = ['event', 'comments']
