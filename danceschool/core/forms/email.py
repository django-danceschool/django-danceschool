from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, HTML, Submit
from dal import autocomplete
import logging
from djangocms_text_ckeditor.widgets import TextEditorWidget
from multi_email_field.forms import MultiEmailField

from ..models import (
    Event, EmailTemplate, get_defaultEmailName, get_defaultEmailFrom
)
from ..utils.emails import get_text_for_html


# Define logger for this file
logger = logging.getLogger(__name__)


class EmailContactForm(forms.Form):

    RICH_TEXT_CHOICES = (
        ('plain', _('Plain text email')),
        ('HTML', _('HTML rich text email'))
    )

    template = forms.ModelChoiceField(
        label=_('(Optional) Select a template'), required=False,
        queryset=EmailTemplate.objects.none()
    )

    richTextChoice = forms.ChoiceField(
        label=_('Send this email as'), widget=forms.RadioSelect,
        choices=RICH_TEXT_CHOICES, required=True, initial='plain'
    )

    subject = forms.CharField(max_length=100)

    message = forms.CharField(widget=forms.Textarea, required=False)
    html_message = forms.CharField(widget=TextEditorWidget, required=False)

    from_name = forms.CharField(max_length=50, initial=get_defaultEmailName)
    from_address = forms.EmailField(max_length=100, initial=get_defaultEmailFrom)
    cc_myself = forms.BooleanField(label=_('CC Myself:'), initial=True, required=False)
    events = forms.ModelMultipleChoiceField(
        label=_('Email all students registered for a current/recent event:'),
        queryset=Event.objects.filter(Q(publicevent__isnull=False) | Q(series__isnull=False)),
        required=False, widget=autocomplete.ModelSelect2Multiple(
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
        )
    )
    include_staff = forms.BooleanField(
        label=_('Include Event Staff'), initial=False, required=False
    )
    testemail = forms.BooleanField(
        label=_('Test email:'), help_text=_('Send a test email to myself only.'),
        initial=False, required=False
    )

    additional_cc = MultiEmailField(
        label=_('Additional Addresses to CC'), help_text=_('One email per line'),
        required=False
    )

    additional_bcc = MultiEmailField(
        label=_('Additional Addresses to BCC'), help_text=_('One email per line'),
        required=False
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        customers = kwargs.pop('customers', [])

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()

        if customers:
            self.fields['customers'] = forms.MultipleChoiceField(
                required=True,
                label=_('Selected customers'),
                widget=forms.CheckboxSelectMultiple(),
                choices=[(x.id, '%s <%s>' % (x.fullName, x.email)) for x in customers]
            )
            self.fields['customers'].initial = [x.id for x in customers]

            customer_section = Div('customers')
            events_section = Div()

        else:
            customer_section = Div()
            events_section = Div('events', 'include_staff')

        if user:
            self.fields['template'].queryset = EmailTemplate.objects.filter(
                Q(groupRequired__isnull=True) | Q(groupRequired__in=user.groups.all())
            ).filter(hideFromForm=False)

        cc_section = Div(
            Div(
                HTML(
                    '<a data-toggle="collapse" href="#collapse_cc">' +
                    ('%s</a> (%s)' % (
                        _('Add CC/BCC recipients'), _('click to expand')
                    ))
                ),
                css_class='card-header'
            ),
            Div(
                'additional_cc', 'additional_bcc',
                css_class='card-body collapse',
                id='collapse_cc',
            ),
            css_class='card my-4'
        )

        self.helper.layout = Layout(
            customer_section,
            'template',
            'richTextChoice',
            'subject',
            'message',
            'html_message',
            'from_name',
            'from_address',
            events_section,
            'cc_myself',
            'testemail',
            cc_section,
            Submit('submit', _('Submit')),
        )

    def clean(self):
        # Custom cleaning ensures email is only sent to one of
        # a set of events or a set of customers
        super().clean()

        # We set to None and don't pop the keys out to prevent
        # KeyError issues with the subsequent view
        customers = self.cleaned_data.get('customers')
        if customers:
            self.cleaned_data['events'] = None
            self.cleaned_data['include_staff'] = None

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
        js = ('js/emailcontact_ajax.js',)
