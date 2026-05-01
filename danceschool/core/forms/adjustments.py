from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.urls import reverse_lazy

from dal import autocomplete
import logging
from django_addanother.widgets import AddAnotherWidgetWrapper

from ..models import Event, Customer, Invoice, Registration, DanceRole


# Define logger for this file
logger = logging.getLogger(__name__)


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


class RegistrationTransferForm(forms.ModelForm):
    '''
    This is the form that is used to transfer an existing EventRegistration
    to another event. It provides a drop-down for selecting an event, along
    with a role selector that auto-updates with the available roles for the
    event. The view will make note of the pricing of the event, but the view
    does not handle price adjustments associated with transferring registrations. 
    '''
    class Meta:
        model = Registration
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.registration = kwargs.pop('instance', None)
        
        for item in self.registration.eventregistration_set.all():

            self.fields['new_customer_%s' % item.id] = forms.ModelChoiceField(
                queryset=Customer.objects.all(),
                label=_('Choose the new customer'),
                required=False,
                widget=AddAnotherWidgetWrapper(
                    autocomplete.ModelSelect2(
                        url='autocompleteCustomer',
                        attrs={
                            # This will set the input placeholder attribute:
                            'data-placeholder': _('Enter customer name or email'),
                            # This will set the yourlabs.Autocomplete.minimumCharacters
                            # options, the naming conversion is handled by jQuery
                            'data-minimum-input-length': 0,
                            'data-max-results': 10,
                            'class': 'modern-style',
                        }
                    ),
                    reverse_lazy('admin:core_customer_add')
                ),
                initial = item.customer
            )

            self.fields['new_event_%s' % item.id] = forms.ModelChoiceField(
                queryset=Event.objects.filter(Q(publicevent__isnull=False) | Q(series__isnull=False)),
                label=_('Choose the new event'),
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
                ),
                initial = item.event
            )

            self.fields['new_role_%s' % item.id] = forms.ModelChoiceField(
                queryset = DanceRole.objects.all(),
                required=False, initial=item.role,
            )

        self.fields['comments'] = forms.CharField(
            label=_('Explanation/Comments (optional)'), required=False,
            help_text=_(
                'This information will be added to the comments on the registration.'
            ),
            widget=forms.Textarea(attrs={
                'placeholder': _('Enter explanation/comments...'),
                'class': 'form-control'
            })
        )

        self.fields['id'] = forms.ModelChoiceField(
            required=True, queryset=Registration.objects.filter(id=self.registration.id),
            widget=forms.HiddenInput(), initial=self.registration.id
        )

    def clean(self):
        cleaned_data = super().clean()
        for id in [
            x.split('_')[-1] for x in cleaned_data.keys()
            if x.startswith('new_event_')
        ]:
            self.clean_new_role(id)

    def clean_new_role(self, id):
        ''' Ensure that the role is valid for the event. '''
        event = self.cleaned_data.get('new_event_%s' % id)
        role = self.cleaned_data.get('new_role_%s' % id)

        if event and role and (role not in event.availableRoles):
            self.add_error(
                'new_role_%s' % id, _('This role is not available for the selected event.')
            )
        return role
