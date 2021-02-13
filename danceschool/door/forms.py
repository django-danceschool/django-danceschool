from django import forms
from django.utils.translation import gettext, gettext_lazy as _
from django.db.models import F, Q, Value, CharField
from django.apps import apps

from dal import autocomplete
from datetime import timedelta
from itertools import chain

from danceschool.core.models import Customer, StaffMember
from danceschool.core.utils.timezone import ensure_localtime


class CustomerGuestAutocompleteForm(forms.Form):
    '''
    This form can be used to search for customers and names on the guest
    list for a night or event.
    '''

    def __init__(self, *args, **kwargs):
        date = kwargs.pop('date', None)

        queryset = Customer.objects.annotate(
            firstName=F('first_name'), lastName=F('last_name'),
            guestType=Value(gettext('Customer'), output_field=CharField())
        ).values('firstName', 'lastName', 'guestType').order_by()
        '''
        queryset = queryset.union(
            StaffMember.objects.annotate(
                guestType=Value(gettext('Customer'), output_field=CharField())
            ).values('firstName', 'lastName', 'guestType').order_by()
        )
        '''
        if apps.is_installed('danceschool.guestlist'):
            GuestListName = apps.get_model('guestlist', 'GuestListName')
            '''
            queryset = queryset.union(
                GuestListName.objects.annotate(
                    guestType=Value(gettext('Customer'), output_field=CharField())
                ).values('firstName', 'lastName', 'guestType').order_by()
            )
            '''
        super().__init__(*args, **kwargs)

        self.fields['date'] = forms.DateField(
            initial=date,
            widget=forms.HiddenInput
        )

        self.fields['name'] = forms.ModelChoiceField(
            queryset=queryset,
            widget=autocomplete.ModelSelect2(
                url='doorRegisterAutocomplete',
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
