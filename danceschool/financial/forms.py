from django import forms
from django.contrib.auth.models import User
from django.core.validators import ValidationError
from django.db.models import Q
from django.forms.widgets import Select
from django.utils.encoding import force_text
from django.utils.safestring import mark_safe
from django.utils.html import format_html
from django.utils.translation import ugettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Div, Submit, HTML
from collections import OrderedDict
from dal import autocomplete
from datetime import datetime
import logging

from danceschool.core.models import EventRegistration, Registration

from .models import ExpenseItem, ExpenseCategory, RevenueItem
from .signals import refund_requested


# Define logger for this file
logger = logging.getLogger(__name__)


RECIPIENT_CHOICES = (
                    (1,_('Me')),
                    (2,_('A Location (e.g. a rental payment)')),
                    (3,_('Someone else')),)

PAYBY_CHOICES = (
                (1,_('Hours of Work/Rental (paid at default rate)')),
                (2,_('Flat Payment')),)

REVENUE_ASSOCIATION_CHOICES = (
                              (2, _('A Class Series or Event')),
                              (3, _('Neither')),)


class ExpenseCategoryWidget(Select):
    # Override render_option to permit extra data of default wage to be used by JQuery
    # This could be optimized to reduce database calls by overriding the render function.

    def render_option(self, selected_choices, option_value, option_label):
        if option_value is None:
            option_value = ''
        option_value = force_text(option_value)
        if option_value in selected_choices:
            selected_html = mark_safe(' selected="selected"')
            if not self.allow_multiple_selected:
                # Only allow for a single selection.
                selected_choices.remove(option_value)
        else:
            selected_html = ''

        # Pass the default wage rate as an option
        if option_value:
            defaultRate = ExpenseCategory.objects.filter(id=int(option_value)).first().defaultRate
            extra_value_data = ' data-defaultRate=' + str(defaultRate)
        else:
            extra_value_data = ''

        return format_html('<option value="{}"{}{}>{}</option>',
                           option_value,
                           selected_html,
                           extra_value_data,
                           force_text(option_label))


class ExpenseReportingForm(forms.ModelForm):
    payTo = forms.ChoiceField(widget=forms.RadioSelect, choices=RECIPIENT_CHOICES,label=_('This expense to be paid to:'),initial=1)
    payBy = forms.ChoiceField(widget=forms.RadioSelect, choices=PAYBY_CHOICES, label=_('Report this expense as:'), initial=1)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        user_id = getattr(user,'id')

        super(ExpenseReportingForm,self).__init__(*args,**kwargs)

        self.helper = FormHelper()

        if user.has_perm('financial.mark_expenses_paid'):
            payment_section = Div(
                Div(
                    HTML('<div class="panel-title"><a data-toggle="collapse" href="#collapsepayment">%s</a> (%s)</div>' % (_('Mark as Approved/Paid'),_('click to expand'))),
                    css_class='panel-heading'
                ),
                Div(
                    'approved',
                    'paid',
                    Div(
                        Field('paymentDate', css_class='datepicker'),
                        'paymentMethod',
                        css_class='form-inline'
                    ),
                    Field('accrualDate', type="hidden",value=datetime.now()),
                    HTML('<p style="margin-top: 30px;"><strong>%s</strong> %s</p>' % (_('Note:'),_('For accounting purposes, please do not mark expenses as paid unless they have already been paid to the recipient.'))),
                    css_class='panel-body collapse',
                    id='collapsepayment',
                ),
                css_class='panel panel-default')
        else:
            payment_section = None

        self.helper.layout = Layout(
            Field('submissionUser', type="hidden", value=user_id),
            Field('payToUser', type="hidden", value=user_id),
            'payTo',
            'payBy',
            'payToLocation',
            'payToName',
            'category',
            'description',
            'hours',
            'total',
            'reimbursement',
            payment_section,
            'attachment',
            Submit('submit',_('Submit')),
        )

    def clean(self):
        # Custom cleaning ensures that user, hours, and total
        # are not reported where not necessary.
        super(ExpenseReportingForm, self).clean()

        payTo = self.cleaned_data.get('payTo')
        payToUser = self.cleaned_data.get('payToUser')
        payToLocation = self.cleaned_data.get('payToLocation')
        payToName = self.cleaned_data.get('payToName')
        payBy = self.cleaned_data.get('payBy')
        hours = self.cleaned_data.get('hours')
        total = self.cleaned_data.get('total')

        paid = self.cleaned_data.get('paid')
        paymentDate = self.cleaned_data.get('paymentDate')

        # Automatically marks expenses that are paid
        # upon submission as accruing at the date of payment.
        if paid:
            self.cleaned_data['accrualDate'] = paymentDate
        else:
            self.cleaned_data.pop('paymentDate',None)

        if payTo != '1' and payToUser:
            self.cleaned_data.pop('payToUser',None)
        if payTo != '2' and payToLocation:
            self.cleaned_data.pop('payToLocation',None)
        if payTo != '3' and payToName:
            self.cleaned_data.pop('payToName',None)

        if payBy == '1' and total:
            self.cleaned_data.pop('total',None)
        if payBy == '2' and hours:
            self.cleaned_data.pop('hours',None)
        return self.cleaned_data

    class Meta:
        model = ExpenseItem
        fields = ['submissionUser','payToUser','payToLocation','payToName','category','description','hours','total','reimbursement','attachment','approved','paid','paymentDate','paymentMethod','accrualDate']
        widgets = {'category': ExpenseCategoryWidget,}

    class Media:
        js = ('js/expense_reporting.js','js/jquery-ui.min.js',)
        css = {
            'all': ('css/jquery-ui.min.css',),
        }


class EventRegistrationChoiceField(forms.ModelChoiceField):
    '''
    This exists so that the validators for EventRegistrations are not
    thrown off by the fact that the initial query is blank.
    '''

    def to_python(self,value):
        try:
            value = super(self.__class__,self).to_python(value)
        except:
            key = self.to_field_name or 'pk'
            value = EventRegistration.objects.filter(**{key: value})
            if not value.exists():
                raise ValidationError(self.error_messages['invalid_choice'], code='invalid_choice')
            else:
                value = value.first()
        return value


class RevenueReportingForm(forms.ModelForm):
    associateWith = forms.ChoiceField(widget=forms.RadioSelect, choices=REVENUE_ASSOCIATION_CHOICES,label=_('This revenue is associated with:'),initial=1)
    currentlyHeldBy = forms.ModelChoiceField(
        queryset=User.objects.filter(Q(is_staff=True) | Q(staffmember__isnull=False)),
        label=_('Cash currently in possession of'),
        required=False,
        widget=autocomplete.ModelSelect2(
            url='autocompleteUser',
            attrs={
                # This will set the input placeholder attribute:
                'data-placeholder': _('Enter a user name'),
                # This will set the yourlabs.Autocomplete.minimumCharacters
                # options, the naming conversion is handled by jQuery
                'data-minimum-input-length': 2,
                'data-max-results': 4,
                'class': 'modern-style',
            }
        )
    )

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', _('Submit')))
        user = kwargs.pop('user', None)

        if hasattr(user,'id'):
            kwargs.update(initial={
                'submissionUser': user.id
            })
        super(RevenueReportingForm,self).__init__(*args,**kwargs)
        self.fields['submissionUser'].widget = forms.HiddenInput()
        self.fields['invoiceNumber'].widget = forms.HiddenInput()
        self.fields["eventregistration"] = EventRegistrationChoiceField(queryset=EventRegistration.objects.none(),required=False)

        # re-order fields to put the associateWith RadioSelect first.
        newFields = OrderedDict()
        newFields['associateWith'] = self.fields['associateWith']
        for key,field in self.fields.items():
            if key not in ['associateWith']:
                newFields[key] = field
        self.fields = newFields

    def clean_description(self):
        ''' Avoid empty descriptions '''
        return self.cleaned_data['description'] or _('Form Submitted Revenue')

    def clean_invoiceNumber(self):
        ''' Create a unique invoice number '''
        return 'SUBMITTED_%s_%s' % (self.cleaned_data['submissionUser'].id,datetime.now().strftime('%Y%m%d%H%M%S'))

    def clean(self):
        # Custom cleaning ensures that revenues are not attributed
        # to both a series and to an event.
        super(RevenueReportingForm, self).clean()

        associateWith = self.cleaned_data.get('associateWith')
        event = self.cleaned_data.get('event')

        if associateWith in ['1','3'] and event:
            self.cleaned_data.pop('event', None)
            self.cleaned_data.pop('eventregistration', None)

        return self.cleaned_data

    class Meta:
        model = RevenueItem
        fields = ['submissionUser','invoiceNumber','category','description','event','eventregistration','receivedFromName','paymentMethod','currentlyHeldBy','total','attachment']

    class Media:
        js = ('js/revenue_reporting.js',)


class RegistrationRefundForm(forms.ModelForm):
    '''
    This is the form that is used to allocate refunds across series and events.  If the Paypal app is installed, then it
    will also be used to submit refund requests to Paypal.  Note that most cleaning validation happens in Javascript.
    '''
    class Meta:
        model = Registration
        fields = []

    def __init__(self, *args, **kwargs):
        super(RegistrationRefundForm, self).__init__(*args, **kwargs)

        reg = kwargs.pop('instance',None)

        for er in reg.eventregistration_set.all():
            self.fields["er_cancelled_%d" % er.id] = forms.BooleanField(
                label=_('Cancelled'),required=False,initial=er.cancelled)
            self.fields["er_refundamount_%d" % er.id] = forms.FloatField(
                label=_('Refund Amount'),required=False,initial=er.revenueRefundsReported,min_value=0,max_value=er.netPrice)

        self.fields['comments'] = forms.CharField(
            label=_('Explanation/Comments (optional)'),required=False,
            help_text=_('This information will be added to the comments on the revenue items associated with this refund.'),
            widget=forms.Textarea(attrs={'placeholder': _('Enter explanation/comments...'), 'class': 'form-control'}))

        self.fields['id'] = forms.ModelChoiceField(
            required=True,queryset=Registration.objects.filter(pk=reg.pk),widget=forms.HiddenInput())

        self.fields['initial_refund_amount'] = forms.FloatField(
            required=True,initial=reg.revenueRefundsReported,min_value=0,max_value=reg.revenueReceivedGross,widget=forms.HiddenInput())

        self.fields['total_refund_amount'] = forms.FloatField(
            required=True,initial=0,min_value=0,max_value=reg.revenueReceivedGross,widget=forms.HiddenInput())

    def clean_total_refund_amount(self):
        '''
        The Javascript should ensure that the hidden input is updated, but double check it here.
        '''
        initial = self.cleaned_data.get('initial_refund_amount', 0)
        total = self.cleaned_data['total_refund_amount']
        summed_refunds = sum([v for k,v in self.cleaned_data.items() if '_refundamount_' in k])

        if summed_refunds != total:
            raise ValidationError(_('Passed value does not match sum of allocated refunds.'))
        elif summed_refunds > self.cleaned_data['id'].revenueReceivedGross:
            raise ValidationError(_('Total refunds allocated exceed revenue received.'))
        elif total < initial:
            raise ValidationError(_('Cannot reduce the total amount of the refund.'))
        return total

    def save(self):
        '''
        Since this form doesn't actually change the Registration object itself, but instead
        the related RevenueItem and other objects, this method is overridden to handle everything correctly,
        rather than performing processing in the view itself.
        '''
        reg = self.instance
        data = self.cleaned_data

        refund_list = [(k.split('_')[0],int(k.split('_')[2]),v) for k,v in data.items() if '_refundamount_' in k]
        comments = data.get('comments','')

        for item in refund_list:
            if item[0] == 'er':
                er = reg.eventregistration_set.get(id=item[1])
                revitem = er.revenueitem_set.first()
                revChanged = False
                cancelled = data.get('er_cancelled_' + str(item[1]))
                if cancelled != er.cancelled:
                    logger.debug(_('Updating cancellation status of EventRegistration %s' % item[1]))
                    er.cancelled = cancelled
                    er.save()
                if revitem.adjustments != -1 * item[2]:
                    logger.debug(_('Updating adjustment to RevenueItem %s, setting adjustments to %s' % (revitem.id,-1 * item[2])))
                    revitem.adjustments = -1 * item[2]
                    revChanged = True
                if comments:
                    revitem.comments = '%s%s\n%s' % (('%s\n\n' % revitem.comments) or '', _('Comment from registration refund form -- %s:' % datetime.now().strftime('%Y-%m-%d %H:%M:%S')),comments)
                    revChanged = True
                if revChanged:
                    revitem.save()

        # Fire the signal indicating that a refund has been processed.  The Paypal app hooks into this.
        additional_refund_amount = data['total_refund_amount'] - data['initial_refund_amount']
        if data['total_refund_amount'] == reg.netPrice:
            refundType = 'Full'
        else:
            refundType = 'Partial'

        if additional_refund_amount > 0:
            logger.debug('Firing signal to handle request.')
            refund_requested.send(
                self,
                registration=reg,
                refundType=refundType,
                refundAmount=additional_refund_amount)

        return reg
