from django import forms
from django.utils.translation import gettext_lazy as _
from django.db.models import F

from dal import autocomplete

from danceschool.core.models import Customer


class CustomerGuestAutocompleteForm(forms.Form):
    '''
    This form can be used to search for customers and names on the guest
    list for a night or event.
    '''

    def __init__(self, *args, **kwargs):
        date = kwargs.pop('date', None)

        super().__init__(*args, **kwargs)

        self.fields['date'] = forms.DateField(
            initial=date,
            widget=forms.HiddenInput
        )

        # Note that the autocomplete works on the unioned queryset of
        # customers, staff, and guests even though the queryset specified here
        # is customers only.  We only specify customers here to avoid issues
        # with filtering unioned querysets.
        self.fields['name'] = forms.ModelChoiceField(
            queryset=Customer.objects.annotate(
                firstName=F('first_name'), lastName=F('last_name')
            ).values('firstName', 'lastName'),
            widget=autocomplete.ModelSelect2(
                url='registerAutocomplete',
                forward=['date'],
                attrs={
                    # This will set the input placeholder attribute:
                    'data-placeholder': _('Enter a name'),
                    # This will set the yourlabs.Autocomplete.minimumCharacters
                    # options, the naming conversion is handled by jQuery
                    'data-minimum-input-length': 2,
                    'data-max-results': 10,
                    'class': 'modern-style',
                    'data-html': True,
                }
            )
        )
