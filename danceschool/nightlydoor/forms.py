from django import forms
from django.utils.translation import ugettext_lazy as _

from dal import autocomplete
from datetime import timedelta
from itertools import chain

from danceschool.core.models import Customer
from danceschool.core.utils.timezone import ensure_localtime


class CustomerGuestAutocompleteForm(forms.Form):
    '''
    This form can be used to search for customers and names on the guest
    list for a night or event.
    '''

    def __init__(self, *args, **kwargs):
        date = kwargs.pop('date', None)
        include_guests = kwargs.pop('includeGuests', True)
        include_customers = kwargs.pop('includeCustomers', True)

        queries = []

        customer_filters = {}
        if date:
            interval_start = ensure_localtime(date)
            interval_end = ensure_localtime(date) + timedelta(days=1)
            customer_filters.update({
                'registration__eventregistration__event__eventoccurrence__endTime__gte': interval_start,
                'registration__eventregistration__event__eventoccurrence__startTime__lte': interval_end,
            })

        if include_customers:
            queries += [Customer.objects.filter(**customer_filters).distinct()]

        queryset = list(chain(*queries))

        super().__init__(*args, **kwargs)

        self.fields['name'] = forms.ModelChoiceField(
            queryset=queryset,
            widget=autocomplete.ModelSelect2(
                url='autocompleteCustomer',
                attrs={
                    # This will set the input placeholder attribute:
                    'data-placeholder': _('Enter a name'),
                    # This will set the yourlabs.Autocomplete.minimumCharacters
                    # options, the naming conversion is handled by jQuery
                    'data-minimum-input-length': 2,
                    'data-max-results': 10,
                    'class': 'modern-style',
                }
            )
        )
