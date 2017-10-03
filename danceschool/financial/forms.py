from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import ValidationError
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.forms.widgets import Select
from django.utils.encoding import force_text
from django.utils.safestring import mark_safe
from django.utils.html import format_html
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Div, Submit, HTML
from collections import OrderedDict
from dal import autocomplete
import logging

from danceschool.core.models import InvoiceItem

from .models import ExpenseItem, ExpenseCategory, RevenueItem, StaffMemberWageInfo
from .autocomplete_light_registry import get_method_list


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
    '''
    Override render_option to permit extra data of default wage to be used by JQuery
    This could be optimized to reduce database calls by overriding the render function.
    '''

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
    paymentMethod = autocomplete.Select2ListCreateChoiceField(
        choice_list=get_method_list,
        required=False,
        widget=autocomplete.ListSelect2(url='paymentMethod-list-autocomplete'),
        label=_('Payment method'),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        user_id = getattr(user,'id')

        super(ExpenseReportingForm,self).__init__(*args,**kwargs)

        self.helper = FormHelper()

        if user.has_perm('financial.mark_expenses_paid'):
            payment_section = Div(
                Div(
                    HTML('<a data-toggle="collapse" href="#collapsepayment">%s</a> (%s)' % (_('Mark as Approved/Paid'),_('click to expand'))),
                    css_class='card-header'
                ),
                Div(
                    'approved',
                    'paid',
                    Div(
                        Field('paymentDate', css_class='datepicker', wrapper_class='col-md-3'),
                        Field('paymentMethod', wrapper_class='col-md-6'),
                        css_class='form-row',
                    ),
                    # The hidden input of accrual date must be passed as a naive datetime.
                    # Django will take care of converting it to local time
                    Field('accrualDate', type="hidden",value=timezone.make_naive(timezone.now()) if timezone.is_aware(timezone.now()) else timezone.now()),
                    HTML('<p style="margin-top: 30px;"><strong>%s</strong> %s</p>' % (_('Note:'),_('For accounting purposes, please do not mark expenses as paid unless they have already been paid to the recipient.'))),
                    css_class='card-body collapse',
                    id='collapsepayment',
                ),
                css_class='card my-4')
        else:
            payment_section = None

        # Add category button should only appear for users who are allowed to add categories
        if user.has_perm('financial.add_expensecategory'):
            related_url = reverse('admin:financial_expensecategory_add') + '?_to_field=id&_popup=1'
            added_html = [
                '<a href="%s" class="btn btn-outline-secondary related-widget-wrapper-link add-related" id="add_id_category"> ' % related_url,
                '<img src="%sadmin/img/icon-addlink.svg" width="10" height="10" alt="%s"/></a>' % (getattr(settings,'STATIC_URL','/static/'), _('Add Another'))
            ]
            category_field = Div(
                Div('category',css_class='col-sm-11'),
                Div(HTML('\n'.join(added_html)),css_class='col-sm-1',style='margin-top: 25px;'),
                css_class='related-widget-wrapper row'
            )
        else:
            category_field = Div('category')

        self.helper.layout = Layout(
            Field('submissionUser', type="hidden", value=user_id),
            Field('payToUser', type="hidden", value=user_id),
            'payTo',
            'payBy',
            'payToLocation',
            'payToName',
            category_field,
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
        if paid and paymentDate:
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
        widgets = {
            'category': ExpenseCategoryWidget,
        }

    class Media:
        js = ('admin/js/admin/RelatedObjectLookups.js','jquery-ui/jquery-ui.min.js','js/expense_reporting.js')
        css = {
            'all': ('jquery-ui/jquery-ui.min.css',),
        }


class InvoiceItemChoiceField(forms.ModelChoiceField):
    '''
    This exists so that the validators for InvoiceItems (EventRegistrations) are not
    thrown off by the fact that the initial query is blank.
    '''

    def to_python(self,value):
        try:
            value = super(self.__class__,self).to_python(value)
        except (ValueError, ValidationError):
            key = self.to_field_name or 'pk'
            value = InvoiceItem.objects.filter(**{key: value})
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
    paymentMethod = autocomplete.Select2ListCreateChoiceField(
        choice_list=get_method_list,
        required=False,
        widget=autocomplete.ListSelect2(url='paymentMethod-list-autocomplete'),
        label=_('Payment method'),
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
        self.fields["invoiceItem"] = InvoiceItemChoiceField(queryset=InvoiceItem.objects.none(),required=False)

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
        return 'SUBMITTED_%s_%s' % (getattr(self.cleaned_data['submissionUser'],'id','None'),timezone.now().strftime('%Y%m%d%H%M%S'))

    def clean(self):
        # Custom cleaning ensures that revenues are not attributed
        # to both a series and to an event.
        super(RevenueReportingForm, self).clean()

        associateWith = self.cleaned_data.get('associateWith')
        event = self.cleaned_data.get('event')

        if associateWith in ['1','3'] and event:
            self.cleaned_data.pop('event', None)
            self.cleaned_data.pop('invoiceItem', None)

        return self.cleaned_data

    class Meta:
        model = RevenueItem
        fields = ['submissionUser','invoiceNumber','category','description','event','invoiceItem','receivedFromName','paymentMethod','currentlyHeldBy','total','attachment']

    class Media:
        js = ('js/revenue_reporting.js',)


class CompensationRuleUpdateForm(forms.ModelForm):
    ''' Used for bulk update of Instructor compensation rules. '''

    def save(self, commit=True):
        ''' Handle the update logic for this in the view, not the form '''
        pass

    class Meta:
        model = StaffMemberWageInfo
        fields = ['category', 'rentalRate','applyRateRule','dayStarts','weekStarts','monthStarts']
