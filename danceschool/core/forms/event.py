from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit
from dal import autocomplete
import logging

from ..models import Event


# Define logger for this file
logger = logging.getLogger(__name__)


class EventAutocompleteForm(forms.Form):
    '''
    This form can be used for views that autocomplete events (e.g. viewing
    registrations), but it has no other fields by default.
    '''

    def __init__(self, *args, **kwargs):
        is_multi = kwargs.pop('multi', False)
        field_class, widget_class = (
            (forms.ModelMultipleChoiceField, autocomplete.ModelSelect2Multiple)
            if is_multi else
            (forms.ModelChoiceField, autocomplete.ModelSelect2)
        )

        # Allows this to be used in cases where the form is associated with a
        # model instance.
        self.instance = kwargs.pop('instance', None)

        super().__init__(*args, **kwargs)

        self.fields['event'] = field_class(
            queryset=Event.objects.filter(Q(publicevent__isnull=False) | Q(series__isnull=False)),
            label=_('Search for an Event'),
            required=True,
            widget=widget_class(
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

        self.helper = FormHelper()
        self.helper.layout = Layout(
            'event',
            Submit('submit', _('Submit'))
        )


class RepeatEventForm(forms.Form):

    startDate = forms.DateField(label=_('First event occurs on'))
    repeatEvery = forms.IntegerField(label=_('Repeat every'), min_value=1, initial=1)
    periodicity = forms.ChoiceField(
        label=_('Period'),
        choices=(('D', _('Days')), ('W', _('Weeks')), ('M', _('Months')),),
        initial='W'
    )
    quantity = forms.IntegerField(
        label=_('Repeat this many times'), min_value=1, max_value=99, required=False
    )
    endDate = forms.DateField(label=_('Repeat until this date'), required=False)

    def clean(self):
        startDate = self.cleaned_data.get('startDate')
        endDate = self.cleaned_data.get('endDate')
        quantity = self.cleaned_data.get('quantity')

        if endDate and not endDate >= startDate:
            self.add_error('endDate', ValidationError(_('End date must be after start date.')))

        if quantity and endDate:
            self.add_error(
                'quantity', ValidationError(_(
                    'Please specify either a number of repeats or an end date, not both.'
                ))
            )
