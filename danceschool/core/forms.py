from django import forms
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.encoding import force_text
from django.forms.widgets import CheckboxSelectMultiple, CheckboxInput, mark_safe, Select
from django.utils.html import conditional_escape, format_html
from django.utils.translation import ugettext_lazy as _, ugettext

from itertools import chain
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML, Hidden, Submit
from dal import autocomplete
from random import random
import json
import logging
from djangocms_text_ckeditor.widgets import TextEditorWidget

from .models import EventStaffMember, SubstituteTeacher, Event, EventOccurrence, Series, SeriesTeacher, Instructor, EmailTemplate, Location, Customer, Invoice, get_defaultEmailName, get_defaultEmailFrom
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
        option_value = force_text(option_value)
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
            room_options = [{'id': x.id, 'name': x.name, 'defaultCapacity': x.defaultCapacity} for x in this_location.room_set.all()]

            extra_value_data = format_html(
                ' data-defaultCapacity="{}" data-roomOptions="{}"',
                defaultCapacity, json.dumps(room_options))
        else:
            extra_value_data = ''

        return format_html('<option value="{}"{}{}>{}</option>',
                           option_value,
                           mark_safe(selected_html),
                           extra_value_data,
                           force_text(option_label))


class CheckboxSelectMultipleWithDisabled(CheckboxSelectMultiple):
    """
    Subclass of Django's checkbox select multiple widget that allows disabling checkbox-options,
    as well as marking some options as subject to override. To disable an option, pass a dict
    instead of a string for its label, of the form: {'label': 'option label', 'disabled': True}.
    To make an option part of a separate "override" choice set, add a dictionary key {'override': True}
    """

    def render(self, name, value, attrs=None, choices=()):
        if value is None:
            value = []
        has_id = attrs and 'id' in attrs
        final_attrs = self.build_attrs(attrs, extra_attrs={'name': name})
        output = [u'',]

        # Separate out regular choices and override-only choices
        all_choices = list(chain(self.choices, choices))

        override_choices = [
            x for x in all_choices if
            isinstance(x[1],dict) and
            'override' in x[1].keys() and
            x[1]['override']
        ]

        regular_choices = [
            x for x in all_choices if x not in override_choices
        ]

        # Normalize to strings
        str_values = set([force_text(v,encoding='utf-8') for v in value])

        if regular_choices:
            output.append(u'<ul class="list-unstyled">')

            for i, (option_value, option_label) in enumerate(regular_choices):
                if 'disabled' in final_attrs:
                    del final_attrs['disabled']
                if isinstance(option_label, dict):
                    if dict.get(option_label, 'disabled'):
                        final_attrs = dict(final_attrs,disabled='disabled')
                    option_label = option_label['label']
                # If an ID attribute was given, add a numeric index as a suffix,
                # so that the checkboxes don't all have the same ID attribute.
                if has_id:
                    final_attrs = dict(final_attrs, id='%s_%s' % (attrs['id'], i))
                    label_for = u' for="%s"' % final_attrs['id']
                else:
                    label_for = ''
                cb = CheckboxInput(final_attrs, check_test=lambda value: value in str_values)
                option_value = force_text(option_value,encoding='utf-8')
                rendered_cb = cb.render(name, option_value)
                option_label = conditional_escape(force_text(option_label,encoding='utf=8'))
                output.append(u'<li><label%s>%s %s</label></li>' % (label_for, rendered_cb, option_label))

            output.append(u'</ul>')

        if override_choices:
            # Determine whether or not to add a Submit button
            submit_button_flag = False

            # Create an ID for the collapse
            if has_id:
                collapse_id = 'override_' + str(attrs['id'])
            else:
                collapse_id = 'override_' + str(int(random() * 10.0**12))

            output.append(u'<button class="btn btn-outline-secondary btn-sm mb-4" type="button" data-toggle="collapse" data-target="#%(id)s">%(string)s</button><div class="collapse" id="%(id)s"><ul class="list-unstyled">' % {'id': collapse_id, 'string': _('Additional Choices')})

            for i, (option_value, option_label) in enumerate(override_choices):
                if 'disabled' in final_attrs:
                    del final_attrs['disabled']
                if isinstance(option_label, dict):
                    if dict.get(option_label, 'disabled'):
                        final_attrs = dict(final_attrs,disabled='disabled')
                    if dict.get(option_label, 'closed'):
                        submit_button_flag = True
                    option_label = option_label['label']
                # If an ID attribute was given, add a numeric index as a suffix,
                # so that the checkboxes don't all have the same ID attribute.
                if has_id:
                    final_attrs = dict(final_attrs, id='%s_%s' % (attrs['id'], i))
                    label_for = u' for="%s"' % final_attrs['id']
                else:
                    label_for = ''
                cb = CheckboxInput(final_attrs, check_test=lambda value: value in str_values)
                option_value = force_text(option_value,encoding='utf=8')
                rendered_cb = cb.render(name, option_value)
                option_label = conditional_escape(force_text(option_label,encoding='utf=8'))
                output.append(u'<li><label%s>%s %s</label></li>' % (label_for, rendered_cb, option_label))
            if submit_button_flag:
                output.append(u'<input class="btn btn-outline-primary btn-sm" type="submit" value="%s &raquo;" />' % _('Register now'))
            output.append(u'</ul></div>')

        return mark_safe(u'\n'.join(output))


class CheckboxSeriesChoiceField(forms.MultipleChoiceField):
    '''
    Inherits from ChoiceField, and uses the widget above, but also
    cleans to raise an error if a user registers as both a lead and a follow,
    or if they register for the whole class plus a drop-in.
    '''
    widget = CheckboxSelectMultipleWithDisabled


class ClassChoiceForm(forms.Form):
    '''
    This is the form that customers use to select classes.
    '''

    def __init__(self,*args,**kwargs):
        openEvents = kwargs.pop('openEvents',Event.objects.none())
        closedEvents = kwargs.pop('closedEvents', Event.objects.none())
        user = kwargs.pop('user',None)

        # Initialize a default (empty) form to fill
        super(ClassChoiceForm, self).__init__(*args, **kwargs)

        # Allow users with appropriate permissions to process door registrations.
        if user and user.has_perm('core.accept_door_payments'):
            self.fields['payAtDoor'] = forms.BooleanField(required=False,label=_('Door/Invoice Registration'))

        if user and user.has_perm('core.override_register_closed'):
            choice_set = openEvents | closedEvents
        else:
            choice_set = openEvents

        # Only the keys passed in this property will be entered into session data.
        # This prevents injection of unknown values into the registration process.
        self.permitted_event_keys = ['role',]

        for event in choice_set:
            field_choices = []

            # Get the set of roles for registration.  If custom roles and capacities
            # are provided, those will be used.  Or, if the DanceType of a Series
            # provides default roles, those will be used.  Otherwise, a single role will
            # be defined as 'Register' .
            eventRoles = event.eventrole_set.all()
            roles = []
            if eventRoles.count() > 0:
                roles = [x.role for x in eventRoles]
            elif isinstance(event,Series) and event.classDescription.danceTypeLevel.danceType.roles.count() > 0:
                roles = event.classDescription.danceTypeLevel.danceType.roles.all()

            # Add one choice per role
            for role in roles:
                this_label = {
                    'label': '%s (%s registered)' % (role.pluralName,event.numRegisteredForRole(role))
                }
                if event.soldOutForRole(role):
                    this_label = {'label': _('%s sold out!') % role.pluralName, 'disabled': True}
                    if user.has_perm('core.override_register_soldout'):
                        this_label['disabled'] = False
                        this_label['override'] = True
                if event in closedEvents:
                    this_label['closed'] = True
                    this_label['override'] = True
                field_choices.append(
                    (json.dumps({'role': role.id,}),this_label)
                )
            # If no choices, then add a general Register choice
            if not roles:
                this_label = {'label': _('Register (%s registered)') % event.numRegistered}
                if event.soldOut:
                    this_label = {'label': _('Sold out!'), 'disabled': True}
                    if user.has_perm('core.override_register_soldout'):
                        this_label['disabled'] = False
                        this_label['override'] = True
                if event in closedEvents:
                    this_label['closed'] = True
                    this_label['override'] = True
                field_choices.append(
                    (json.dumps({'role': None}),this_label)
                )

            # Add drop-in choices if they are available and if this user has permission.
            # If the user only has override permissions, add the override collapse only.
            # Note that this works because django-polymorphic returns the subclass.
            if isinstance(event,Series):
                if event.allowDropins and user and user.has_perm('core.register_dropins'):
                    for occurrence in event.eventoccurrence_set.all():
                        field_choices += ((json.dumps({'dropin_' + str(occurrence.id): True}), _('Drop-in: ') + ensure_localtime(occurrence.startTime).strftime('%B %-d')),)
                        self.permitted_event_keys.append('dropin_' + str(occurrence.id))
                elif (user and user.has_perm('core.override_register_dropins')):
                    for occurrence in event.eventoccurrence_set.all():
                        field_choices += ((json.dumps({'dropin_' + str(occurrence.id): True}),{'label': _('Drop-in: ') + ensure_localtime(occurrence.startTime).strftime('%B %-d'),'override':True}),)
                        self.permitted_event_keys.append('dropin_' + str(occurrence.id))

            self.fields['event_' + str(event.id)] = CheckboxSeriesChoiceField(
                label=event.name,
                choices=field_choices,
                required=False,
            )

    def clean(self):
        # Check that the registration is not empty
        cleaned_data = super(ClassChoiceForm,self).clean()
        hasContent = False

        for key,value in cleaned_data.items():
            if value and key != 'payAtDoor':
                hasContent = True
            if isinstance(value,list):
                # Ignore any passed value that is not a dictionary
                value_dict_list = [json.loads(x) for x in value if isinstance(json.loads(x),dict)]

                # Get the list of roles -- if more than one, then raise an error
                roles = [y.pop('role') for y in value_dict_list if y.get('role')]
                value_dict = {}
                for v in value_dict_list:
                    value_dict.update(v)

                # Get the list of dropIns
                dropIns = [k.replace('dropin_','') for k in value_dict.keys() if 'dropin_' in k]

                if len(roles) > 1:
                    raise ValidationError(_('Must select only one role.'),code='invalid')
                elif len(roles) == 1 and len(dropIns) > 0:
                    raise ValidationError(_('Cannot register for drop-in classes and also for the entire series.'),code='invalid')
        if not hasContent:
            raise ValidationError(_('Must register for at least one class or series.'))


class RegistrationContactForm(forms.Form):
    '''
    This is the form customers use to fill out their contact info.
    '''

    firstName = forms.CharField(label=_('First Name'))
    lastName = forms.CharField(label=_('Last Name'))
    email = forms.EmailField()
    phone = forms.CharField(required=False,label=_('Telephone (optional)'),help_text=_('We may use this to notify you in event of a cancellation.'))
    student = forms.BooleanField(required=False,label=_('I am a student'), help_text=_('Photo ID is required at the door'))
    mailList = forms.BooleanField(required=False,label=_('Add me to the mailing list'))
    agreeToPolicies = forms.BooleanField(required=True,label=_('<strong>I agree to all policies (required)</strong>'),help_text=_('By checking, you agree to abide by all policies.'))
    gift = forms.CharField(required=False,label=_('Voucher ID'))
    howHeardAboutUs = forms.ChoiceField(choices=HOW_HEARD_CHOICES,required=False,label=_('How did you hear about us?'),help_text=_('Optional'))
    comments = forms.CharField(widget=forms.Textarea,required=False,label=_('Comments'),help_text=_('Add anything else you\'d like to tell us.'))

    def get_top_layout(self):

        top_layout = Layout(
            Div(
                Field('firstName', wrapper_class='col'),
                Field('lastName', wrapper_class='col'),
                css_class='row'
            ),
            Div(
                Field('email', wrapper_class='col'),
                Field('phone',wrapper_class='col'),
                css_class='row'
            ),
        )
        return top_layout

    def get_mid_layout(self):
        mid_layout = Layout(
            Div('agreeToPolicies','student',css_class='card card-body bg-light my-2'),
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

    def __init__(self,*args,**kwargs):
        self._request = kwargs.pop('request',None)
        self._registration = kwargs.pop('registration',None)
        user = getattr(self._request,'user',None)
        session = getattr(self._request,'session',{}).get(REG_VALIDATION_STR,{})

        super(RegistrationContactForm,self).__init__(*args,**kwargs)
        self._session = session

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = False  # Our template must explicitly include the <form tag>

        if user and hasattr(user,'customer') and user.customer and not session.get('payAtDoor',False):
            # Input existing info for users who are logged in and have signed up before
            self.fields['firstName'].initial = user.customer.first_name or user.first_name
            self.fields['lastName'].initial = user.customer.last_name or user.last_name
            self.fields['email'].initial = user.customer.email or user.email
            self.fields['phone'].initial = user.customer.phone

        self.helper.layout = Layout(
            self.get_top_layout(),
            self.get_mid_layout(),
            self.get_bottom_layout(),
            Submit('submit',_('Complete Registration'))
        )

        # If a voucher ID was passed (i.e. a referral code), then populate the form
        # and clear the passed session value
        session['gift'] = ''
        if session.get('voucher_id'):
            self.fields['gift'].initial = session.get('voucher_id')
            session['voucher_id'] = None

    def is_valid(self):
        '''
        For this form to be considered valid, there must be not only no errors, but also no messages on
        the request that need to be shown.
        '''

        valid = super(RegistrationContactForm,self).is_valid()
        msgs = messages.get_messages(self._request)

        # We only want validation messages to show up once, so pop messages that have already show up
        # before checking to see if any messages remain to be shown.
        prior_messages = self._session.pop('prior_messages',[])
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

    def clean(self):
        super(RegistrationContactForm,self).clean()
        first = self.cleaned_data.get('firstName')
        last = self.cleaned_data.get('lastName')
        email = self.cleaned_data.get('email')

        # Check that this customer is not already registered for any of the Events in the list
        customer = Customer.objects.filter(
            first_name=first,
            last_name=last,
            email=email).first()

        if customer:
            eventids = [x.event.id for x in self._registration.temporaryeventregistration_set.all()]
            already_registered_list = customer.getSeriesRegistered().filter(id__in=eventids)
        else:
            already_registered_list = []

        if already_registered_list:
            error_list = '\n'.join(['<li>%s</li>' % (x.name,) for x in already_registered_list])
            raise ValidationError(ugettext(mark_safe('You are already registered for:\n<ul>\n%s\n</ul>\nIf you are registering another person, please enter their name.' % error_list)))

        # Allow other handlers to add validation errors to the form.  Also, by passing the request, we allow
        # those handlers to add messages to the request, which (for this form) are treated like errors in that
        # they prevent the form from being considered valid.
        check_student_info.send(sender=RegistrationContactForm,instance=self,formData=self.cleaned_data,request=self._request,registration=self._registration)

        return self.cleaned_data


class DoorAmountForm(forms.Form):
    '''
    This is the form that staff users fill out to indicate that they received a cash
    payment.  Upon this being marked, the registration is processed.
    '''

    submissionUser = forms.ModelChoiceField(queryset=User.objects.filter(Q(staffmember__isnull=False) | Q(is_staff=True)),required=True)

    paid = forms.BooleanField(label=_('Payment Received'),required=False)
    receivedBy = forms.ModelChoiceField(
        queryset=User.objects.filter(Q(staffmember__isnull=False) | Q(is_staff=True)),
        label=_('Payment received by:'),
        required=False,
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
    amountPaid = forms.FloatField(label=_('Amount Paid'),required=False)

    invoiceSent = forms.BooleanField(label=_('Send Invoice'),required=False)
    cashPayerEmail = forms.EmailField(label=_('Payer Email Address'),required=False)
    invoicePayerEmail = forms.EmailField(label=_('Payer Email Address'),required=False)
    discountAmount = forms.FloatField(required=False)

    def __init__(self,*args,**kwargs):
        user = kwargs.pop('user',None)
        payerEmail = kwargs.pop('payerEmail',None)
        doorPortion = kwargs.pop('doorPortion', None)
        invoicePortion = kwargs.pop('invoicePortion', None)
        discountAmount = kwargs.pop('discountAmount', None)

        subUser = getattr(user,'id',None)

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = False  # Our template must explicitly include the <form tag>

        if doorPortion:
            door_layout = Layout(
                HTML("""
                    <div class="card mt-4">
                        <h6 class="card-header" role="tab" id="door_headingOne">
                            """ + str(_('Cash Payment')) + """
                        </h6>
                        <div class="card-body">
                    """),
                'paid',
                'receivedBy',
                'amountPaid',
                'cashPayerEmail',
                Submit('submit','Submit'),
                HTML("""
                        </div>
                    </div>
                """),
            )
        else:
            door_layout = Layout(HTML(""))

        if invoicePortion:
            invoice_layout = Layout(
                HTML("""
                    <div class="card mt-4">
                        <h6 class="card-header" role="tab" id="door_headingTwo">
                                """ + str(_('Send Invoice')) + """
                        </h6>
                        <div class="card-body">
                    """),
                'invoiceSent',
                'invoicePayerEmail',
                Hidden('discountAmount', discountAmount),
                Submit('submit','Submit'),
                HTML("""
                        </div>
                    </div>
                """),
            )
        else:
            invoice_layout = Layout(HTML(""))

        self.helper.layout = Layout(
            HTML('<div id="door_accordion" role="tablist" aria-multiselectable="true">'),
            Hidden('submissionUser',subUser),
            door_layout,
            invoice_layout,
            HTML('</div>')
        )

        kwargs.update(initial={
            'cashPayerEmail': payerEmail,
            'invoicePayerEmail': payerEmail,
            'receivedBy': subUser,
        })

        super(DoorAmountForm,self).__init__(*args, **kwargs)

    def clean_submissionUser(self):
        paid = self.data.get('paid') or None
        invoiceSent = self.data.get('invoiceSent') or None

        user_id = self.data.get('submissionUser') or None

        if user_id:
            user = User.objects.get(id=user_id)
        if not user_id or not user:
            raise ValidationError(_('submissionUser not found.'))

        elif paid and not user.has_perm('core.accept_door_payments'):
            raise ValidationError(_('Invalid user submitted door payment.'))
        elif invoiceSent and not user.has_perm('core.send_invoices'):
            raise ValidationError(_('Invalid user submitted invoice.'))
        return user

    def clean(self):
        form_data = self.cleaned_data

        logger.debug('Form Data:\n%s' % form_data)

        paid = form_data.get('paid')
        invoiceSent = form_data.get('invoiceSent')

        if paid and invoiceSent:
            raise ValidationError(_('Must choose either cash payment or invoice submission, not both.'))

        if not paid and not invoiceSent:
            raise ValidationError(_('Must select either cash payment or invoice submission.'))

        # Check for required values here because the form can be used in two ways.
        if paid:
            if not form_data.get('submissionUser'):
                raise ValidationError(_('Submission user is required.'))
            if not form_data.get('receivedBy'):
                raise ValidationError(_('Must specify recipient of the money.'))
            if not form_data.get('amountPaid'):
                raise ValidationError(_('Must specify the amount of the payment.'))

        if invoiceSent:
            if not form_data.get('submissionUser'):
                raise ValidationError(_('Submission user is required.'))
            if not form_data.get('invoicePayerEmail'):
                raise ValidationError(_('Must specify the email address of the invoice recipient.'))

        return form_data


class RefundForm(forms.ModelForm):
    '''
    This is the form that is used to allocate refunds across series and events.  If the Paypal app is installed, then it
    will also be used to submit refund requests to Paypal.  Note that most cleaning validation happens in Javascript.
    '''
    class Meta:
        model = Invoice
        fields = []

    def __init__(self, *args, **kwargs):
        super(RefundForm, self).__init__(*args, **kwargs)

        this_invoice = kwargs.pop('instance',None)

        for item in this_invoice.invoiceitem_set.all():
            initial = False
            if item.finalEventRegistration:
                initial = item.finalEventRegistration.cancelled
            item_max = item.total + item.taxes if this_invoice.buyerPaysSalesTax else item.total

            self.fields["item_cancelled_%s" % item.id] = forms.BooleanField(
                label=_('Cancelled'),required=False,initial=initial)
            self.fields['item_refundamount_%s' % item.id] = forms.FloatField(
                label=_('Refund Amount'),required=False,initial=(-1) * item.adjustments, min_value=0, max_value=item_max)

        self.fields['comments'] = forms.CharField(
            label=_('Explanation/Comments (optional)'),required=False,
            help_text=_('This information will be added to the comments on the invoice associated with this refund.'),
            widget=forms.Textarea(attrs={'placeholder': _('Enter explanation/comments...'), 'class': 'form-control'}))

        self.fields['id'] = forms.ModelChoiceField(
            required=True,queryset=Invoice.objects.filter(id=this_invoice.id),widget=forms.HiddenInput(),initial=this_invoice.id)

        self.fields['initial_refund_amount'] = forms.FloatField(
            required=True,initial=(-1) * this_invoice.adjustments,min_value=0,max_value=this_invoice.amountPaid + this_invoice.refunds,widget=forms.HiddenInput())

        self.fields['total_refund_amount'] = forms.FloatField(
            required=True,initial=0,min_value=0,max_value=this_invoice.amountPaid + this_invoice.refunds,widget=forms.HiddenInput())

    def clean_total_refund_amount(self):
        '''
        The Javascript should ensure that the hidden input is updated, but double check it here.
        '''
        initial = self.cleaned_data.get('initial_refund_amount', 0)
        total = self.cleaned_data['total_refund_amount']
        summed_refunds = sum([v for k,v in self.cleaned_data.items() if k.startswith('item_refundamount_')])

        if not self.cleaned_data.get('id'):
            raise ValidationError('ID not in cleaned data')

        if summed_refunds != total:
            raise ValidationError(_('Passed value does not match sum of allocated refunds.'))
        elif summed_refunds > self.cleaned_data['id'].amountPaid + self.cleaned_data['id'].refunds:
            raise ValidationError(_('Total refunds allocated exceed revenue received.'))
        elif total < initial:
            raise ValidationError(_('Cannot reduce the total amount of the refund.'))
        return total


class EmailContactForm(forms.Form):

    EMAIL_SENDTOSET_CHOICES = (('series',_('All students in one or more series')),('month',_('All Students in a given month')))
    RICH_TEXT_CHOICES = (('plain',_('Plain text email')),('HTML',_('HTML rich text email')))

    sendToSet = forms.ChoiceField(label=_('This email is for:'),widget=forms.RadioSelect,choices=EMAIL_SENDTOSET_CHOICES,required=False,initial='series')

    template = forms.ModelChoiceField(label=_('(Optional) Select a template'),required=False,queryset=EmailTemplate.objects.none())

    richTextChoice = forms.ChoiceField(label=_('Send this email as'),widget=forms.RadioSelect,choices=RICH_TEXT_CHOICES,required=True,initial='plain')

    subject = forms.CharField(max_length=100)

    message = forms.CharField(widget=forms.Textarea,required=False)
    html_message = forms.CharField(widget=TextEditorWidget,required=False)

    from_name = forms.CharField(max_length=50,initial=get_defaultEmailName)
    from_address = forms.EmailField(max_length=100,initial=get_defaultEmailFrom)
    cc_myself = forms.BooleanField(label=_('CC Myself:'),initial=True,required=False)
    month = forms.ChoiceField(label=_('Email all students registered in month:'),initial='',required=False)
    series = forms.MultipleChoiceField(label=_('Email all students registered in a current/recent series:'),initial='',required=False)
    testemail = forms.BooleanField(label=_('Test email:'),help_text=_('Send a test email to myself only.'),initial=False,required=False)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user',None)
        months = kwargs.pop('months',[])
        recentseries = kwargs.pop('recentseries',[])
        customers = kwargs.pop('customers',[])

        super(EmailContactForm, self).__init__(*args, **kwargs)

        if customers:
            self.fields['customers'] = forms.MultipleChoiceField(
                required=True,
                label=_('Selected customers'),
                widget=forms.CheckboxSelectMultiple(),
                choices=[(x.id,'%s <%s>' % (x.fullName, x.email)) for x in customers]
            )
            self.fields['customers'].initial = [x.id for x in customers]
            self.fields.pop('month',None)
            self.fields.pop('series',None)
            self.fields.pop('sendToSet',None)

            # Move the customer list to the top of the form
            self.fields.move_to_end('customers',last=False)

        else:
            self.fields['month'].choices = months
            self.fields['series'].choices = recentseries

        if user:
            self.fields['template'].queryset = EmailTemplate.objects.filter(Q(groupRequired__isnull=True) | Q(groupRequired__in=user.groups.all())).filter(hideFromForm=False)

    def clean(self):
        # Custom cleaning ensures email is only sent to one of
        # a series, a month, or a set of customers
        super(EmailContactForm, self).clean()

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
        js = ('js/emailcontact_sendToSet.js','js/emailcontact_ajax.js')


class SeriesTeacherChoiceField(forms.ModelChoiceField):
    '''
    This exists so that the validators for substitute teaching are not
    thrown off by the fact that the initial query is blank.
    '''

    def to_python(self,value):
        try:
            value = super(SeriesTeacherChoiceField,self).to_python(value)
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
        pks = set(force_text(getattr(o, key)) for o in qs)
        for val in value:
            if force_text(val) not in pks:
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
        kwargs['initial'] = kwargs.get('initial',{})
        kwargs['initial'].update({'category': getConstant('general__eventStaffCategorySubstitute').id})

        # If the user is a staffMember, then populate the form with their info
        if hasattr(user,'staffmember'):
            kwargs['initial'].update({
                'staffMember': user.staffmember,
                'submissionUser': user,
            })

        super(SubstituteReportingForm,self).__init__(*args,**kwargs)
        self.fields['event'] = forms.ModelChoiceField(queryset=Series.objects.order_by('-startTime'))
        self.fields['staffMember'] = forms.ModelChoiceField(queryset=Instructor.objects.exclude(
            status__in=[
                Instructor.InstructorStatus.hidden,
                Instructor.InstructorStatus.retired,
                Instructor.InstructorStatus.retiredGuest
            ]).order_by('status','lastName','firstName'))
        self.fields['replacedStaffMember'] = SeriesTeacherChoiceField(queryset=SeriesTeacher.objects.none())
        self.fields['occurrences'] = SeriesClassesChoiceField(queryset=EventOccurrence.objects.none())
        self.fields['submissionUser'].widget = forms.HiddenInput()
        self.fields['category'].widget = forms.HiddenInput()

    def clean(self):
        '''
        This code prevents multiple individuals from substituting for the
        same class and class teacher.  It also prevents an individual from
        substituting for a class in which they are a teacher.
        '''
        super(SubstituteReportingForm,self).clean()

        occurrences = self.cleaned_data.get('occurrences',[])
        staffMember = self.cleaned_data.get('staffMember')
        replacementFor = self.cleaned_data.get('replacedStaffMember',[])
        event = self.cleaned_data.get('event')

        for occ in occurrences:
            for this_sub in occ.eventstaffmember_set.all():
                if this_sub.replacedStaffMember == replacementFor:
                    self.add_error('occurrences',ValidationError(_('One or more classes you have selected already has a substitute teacher for that class.'),code='invalid'))

        if event and staffMember:
            if staffMember in [x.staffMember for x in event.eventstaffmember_set.filter(category__in=[getConstant('general__eventStaffCategoryAssistant'),getConstant('general__eventStaffCategoryInstructor')])]:
                self.add_error('event',ValidationError(_('You cannot substitute teach for a class in which you were an instructor.'),code='invalid'))

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
            return super(SubstituteReportingForm,self).save()

    class Meta:
        model = SubstituteTeacher
        exclude = []

    class Media:
        js = ('js/substituteteacher_ajax.js',)


class InstructorBioChangeForm(forms.ModelForm):

    class Meta:
        model = Instructor
        fields = ['publicEmail','privateEmail','phone','availableForPrivates']


class RepeatEventForm(forms.Form):

    startDate = forms.DateField(label=_('First event occurs on'))
    repeatEvery = forms.IntegerField(label=_('Repeat every'),min_value=1, initial=1)
    periodicity = forms.ChoiceField(label=_('Period'),choices=(('D',_('Days')),('W',_('Weeks')),('M',_('Months')),), initial='W')
    quantity = forms.IntegerField(label=_('Repeat this many times'),min_value=1,max_value=99,required=False)
    endDate = forms.DateField(label=_('Repeat until this date'),required=False)

    def clean(self):
        startDate = self.cleaned_data.get('startDate')
        endDate = self.cleaned_data.get('endDate')
        quantity = self.cleaned_data.get('quantity')

        if endDate and not endDate >= startDate:
            self.add_error('endDate',ValidationError(_('End date must be after start date.')))

        if quantity and endDate:
            self.add_error('quantity',ValidationError(_('Please specify either a number of repeats or an end date, not both.')))


class InvoiceNotificationForm(forms.Form):
    '''
    This form just allows customers to deselect invoices for notification.
    '''

    def __init__(self,*args,**kwargs):
        invoices = kwargs.pop('invoices',Invoice.objects.none())

        # Initialize a default (empty) form to fill
        super(InvoiceNotificationForm, self).__init__(*args, **kwargs)

        for invoice in invoices:
            self.fields['invoice_%s' % invoice.id] = forms.BooleanField(label=invoice.id, required=False,initial=True)
