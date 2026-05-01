from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.encoding import force_str
from django.utils.translation import gettext_lazy as _

from dal import autocomplete
import logging

from ..models import (
    EventStaffMember, SubstituteTeacher, Event, EventOccurrence,
    StaffMember
)
from ..constants import getConstant


# Define logger for this file
logger = logging.getLogger(__name__)


class StaffChoiceField(forms.ModelChoiceField):
    '''
    This exists so that the validators for substitute staffing are not
    thrown off by the fact that the initial query is blank.
    '''

    def to_python(self, value):
        try:
            value = super().to_python(value)
        except (ValueError, ValidationError):
            key = self.to_field_name or 'pk'
            value = EventStaffMember.objects.filter(**{key: value})
            if not value.exists():
                raise ValidationError(self.error_messages['invalid_choice'], code='invalid_choice')
            else:
                value = value.first()
        return value


class OccurrenceChoiceField(forms.ModelMultipleChoiceField):
    '''
    This exists so that the validators for staff substitutions are not
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
        pks = set(force_str(getattr(o, key)) for o in qs)
        for val in value:
            if force_str(val) not in pks:
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
        kwargs['initial'] = kwargs.get('initial', {})
        kwargs['initial'].update(
            {'category': getConstant('general__eventStaffCategorySubstitute').id}
        )

        # If the user is a staffMember, then populate the form with their info
        if hasattr(user, 'staffmember'):
            kwargs['initial'].update({
                'staffMember': user.staffmember,
                'submissionUser': user,
            })

        super().__init__(*args, **kwargs)
        self.fields['event'] = forms.ModelChoiceField(
            queryset=Event.objects.filter(Q(publicevent__isnull=False) | Q(series__isnull=False)),
            label=_('Event'),
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
            )
        )

        self.fields['staffMember'] = forms.ModelChoiceField(
            queryset=StaffMember.objects.all(),
            widget=autocomplete.ModelSelect2(
                url='autocompleteStaffMember',
                attrs={
                    # This will set the input placeholder attribute:
                    'data-placeholder': _('Enter a staff member name'),
                    # This will set the yourlabs.Autocomplete.minimumCharacters
                    # options, the naming conversion is handled by jQuery
                    'data-minimum-input-length': 1,
                    'data-max-results': 10,
                    'class': 'modern-style',
                },
            )
        )

        self.fields['replacedStaffMember'] = StaffChoiceField(
            queryset=EventStaffMember.objects.none()
        )
        self.fields['occurrences'] = OccurrenceChoiceField(queryset=EventOccurrence.objects.none())
        self.fields['submissionUser'].widget = forms.HiddenInput()

    def clean(self):
        '''
        This code prevents multiple individuals from substituting for the
        same class and class teacher.  It also prevents an individual from
        substituting for a class in which they are a teacher.
        '''
        super().clean()

        category = self.cleaned_data.get('category')
        occurrences = self.cleaned_data.get('occurrences', [])
        staffMember = self.cleaned_data.get('staffMember', [])
        replacementFor = self.cleaned_data.get('replacedStaffMember', [])

        if getattr(replacementFor, 'staffMember', []) == staffMember:
            self.add_error(
                'replacedStaffMember',
                ValidationError(
                    _('Staffers cannot substitute for themselves.'),
                    code='invalid'
                )
            )

        for occ in occurrences:
            for this_sub in occ.eventstaffmember_set.all():
                if this_sub.replacedStaffMember == replacementFor:
                    self.add_error(
                        'occurrences',
                        ValidationError(_(
                            'The staff member you selected has already ' +
                            'been reported as replaced for one or more occurrences.'
                        ), code='invalid')
                    )

        if replacementFor and not (
            category == replacementFor.category or
            (
                category == getConstant('general__eventStaffCategorySubstitute') and
                replacementFor.category in [
                    getConstant('general__eventStaffCategoryAssistant'),
                    getConstant('general__eventStaffCategoryInstructor')
                ]
            )
        ):
            self.add_error('replacedStaffMember', ValidationError(_(
                'Replaced staff member was not scheduled for this category of staffing.'
            ), code='invalid'))

    def validate_unique(self):
        '''
        We don't need to check the unique_together constraint in this form, because if the
        constraint is not satisfied, then the form will just update the existing instance
        in the save() method below.
        '''
        pass

    def save(self, commit=True):
        '''
        If a staff member is reporting substitution for a second time, then we should update
        the list of occurrences for which they are a substitute on their existing EventStaffMember
        record, rather than creating a new record and creating database issues.
        '''

        replaced = self.cleaned_data.get('replacedStaffMember')
        occs = self.cleaned_data.get('occurrences')

        existing_record = EventStaffMember.objects.filter(
            staffMember=self.cleaned_data.get('staffMember'),
            event=self.cleaned_data.get('event'),
            category=self.cleaned_data.get('category'),
            replacedStaffMember=self.cleaned_data.get('replacedStaffMember'),
        )

        if existing_record.exists():
            record = existing_record.first()
            for x in occs:
                record.occurrences.add(x)
            record.save()
        else:
            record = super().save()

        # Remove the substituted occurrences from the replaced staff member. If
        # there are no occurrences left, then drop the staffer entirely.
        for x in occs:
            replaced.occurrences.remove(x)
        if replaced.occurrences.count() == 0:
            replaced.delete()
        return record

    class Meta:
        model = SubstituteTeacher
        exclude = ['data',]

    class Media:
        js = ('js/substituteteacher_ajax.js',)


class StaffMemberBioChangeForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        # Initialize a default form to fill
        super().__init__(*args, **kwargs)

        # If the individual is an instructor, then add the availableForPrivates field
        if getattr(self.instance, 'instructor', None):
            self.fields['availableForPrivates'] = forms.BooleanField(
                label=_('Available For private lessons'),
                initial=True,
                required=False,
                help_text=_(
                    'Check this box if you would like to be listed as ' +
                    'available for private lessons from students.'
                )
            )

    def save(self, commit=True):
        '''
        If the staff member is an instructor, also update the availableForPrivates
        field on the Instructor record.
        '''
        if getattr(self.instance, 'instructor', None):
            self.instance.instructor.availableForPrivates = self.cleaned_data.pop(
                'availableForPrivates', self.instance.instructor.availableForPrivates
            )
            self.instance.instructor.save(update_fields=['availableForPrivates', ])
        super().save(commit=True)

    class Meta:
        model = StaffMember
        fields = ['publicEmail', 'privateEmail', 'phone']
