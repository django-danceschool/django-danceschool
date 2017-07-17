from django import forms
from django.utils.translation import ugettext_lazy as _


class VoucherCustomizationForm(forms.Form):

    emailTo = forms.EmailField(label=_('Email gift certificate to'),required=True)
    emailType = forms.ChoiceField(
        label=_('This email belongs to'),
        widget=forms.RadioSelect,
        required=True,
        choices=[('R',_('The recipient')),('P',_('The purchaser'))],
        help_text=_('If emailing directly to the recipient, a gift message will be sent. If emailing to the purchaser, the gift message will only be included as a PDF attachment.')
    )

    recipientName = forms.CharField(label=_('Recipient name (optional)'),required=False,help_text=_('If provided, this will be used to customize the gift message.'))
    fromName = forms.CharField(label=_('From name (optional)'),required=False)

    message = forms.CharField(label=_('Enter a message to the recipient (optional)'),required=False)
