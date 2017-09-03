from django import forms
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from django.core.exceptions import ValidationError

from datetime import datetime, timedelta

from danceschool.core.constants import getConstant
from danceschool.core.models import DanceRole, Location, Instructor, PricingTier
from danceschool.core.utils.timezone import ensure_localtime

from .models import InstructorAvailabilitySlot


def get_duration_choices():
    return [(x,x) for x in range(
        getConstant('privateLessons__minimumLessonLength'),
        getConstant('privateLessons__maximumLessonLength') + 1,
        getConstant('privateLessons__lessonLengthInterval'),
    )]


def get_default_duration():
    return getConstant('privateLessons__defaultLessonLength')


class SlotBookingForm(forms.Form):
    slotId = forms.IntegerField(required=True,widget=forms.HiddenInput)
    duration = forms.ChoiceField(label=_('Duration'),choices=get_duration_choices,initial=get_default_duration)
    role = forms.ChoiceField(label=_('Dance role'),choices=[(x.id, x.name) for x in DanceRole.objects.all()])
    participants = forms.IntegerField(label=_('Expected # Participants'),initial=1, min_value=1, help_text=_('Be advised that group lessons may be charged a different rate.'))
    comments = forms.CharField(label=_('Comments/Notes'), required=False, help_text=_('Please enter any comments or notes that you would like to be provided to the instructor before the lesson, such as the topics on which you may want to focus.'))

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user',None)

        # Initialize the default form
        super(SlotBookingForm, self).__init__(*args, **kwargs)

        # Allow users with appropriate permissions to process door registrations.
        if user and user.has_perm('core.accept_door_payments'):
            self.fields['payAtDoor'] = forms.BooleanField(required=False,label=_('Door/Invoice Registration'))


class SlotCreationForm(forms.Form):
    instructorId = forms.ModelChoiceField(label=_('Instructor'),queryset=Instructor.objects.all(),widget=forms.HiddenInput,required=True)

    startDate = forms.DateField(label=_('Start date'),required=True,widget=forms.HiddenInput)
    endDate = forms.DateField(label=_('End date'),required=True,widget=forms.HiddenInput)
    startTime = forms.TimeField(
        label=_('Start time'),required=True,
        input_formats=getattr(settings,'TIME_INPUT_FORMATS',[]) + ['%I:%M %p','%-I:%M %p','%I:%M%p','%-I:%M%p']
    )
    endTime = forms.TimeField(
        label=_('End time'),required=True,
        input_formats=getattr(settings,'TIME_INPUT_FORMATS',[]) + ['%I:%M %p','%-I:%M %p','%I:%M%p','%-I:%M%p'],
    )

    location = forms.ModelChoiceField(label=_('Location'),queryset=Location.objects.exclude(status=Location.StatusChoices.former),required=False)
    pricingTier = forms.ModelChoiceField(
        label=_('Pricing Tier'),queryset=PricingTier.objects.filter(expired=False),required=False,
        help_text=_('A pricing tier is required for online registration and payment. If your school handles scheduling, but not payment for lessons, then leave this blank.')
    )
    status = forms.ChoiceField(label=_('Initial Status'),required=True,choices=InstructorAvailabilitySlot.SlotStatus.choices, initial=InstructorAvailabilitySlot.SlotStatus.available)

    def clean(self):
        '''
        Only allow submission if there are not already slots in the submitted window.
        '''

        super(SlotCreationForm,self).clean()

        startDate = self.cleaned_data.get('startDate')
        endDate = self.cleaned_data.get('endDate')
        startTime = self.cleaned_data.get('startTime')
        endTime = self.cleaned_data.get('endTime')
        instructor = self.cleaned_data.get('instructorId')

        existingSlots = InstructorAvailabilitySlot.objects.filter(
            instructor=instructor,
            startTime__gt=(
                ensure_localtime(datetime.combine(startDate,startTime)) -
                timedelta(minutes=getConstant('privateLessons__lessonLengthInterval'))
            ),
            startTime__lt=ensure_localtime(datetime.combine(endDate,endTime)),
        )

        if existingSlots.exists():
            raise ValidationError(_('Newly created slots cannot overlap existing slots for this instructor.'),code='invalid')


class SlotUpdateForm(forms.Form):
    slotIds = forms.ModelMultipleChoiceField(required=True,widget=forms.MultipleHiddenInput,queryset=InstructorAvailabilitySlot.objects.all())

    updateStatus = forms.ChoiceField(label=_('Update Status'),required=True,choices=InstructorAvailabilitySlot.SlotStatus.choices, initial=InstructorAvailabilitySlot.SlotStatus.available)
    updateLocation = forms.ModelChoiceField(label=_('Update Location'),queryset=Location.objects.exclude(status=Location.StatusChoices.former),required=False)
    updatePricing = forms.ModelChoiceField(
        label=_('Update pricing'),queryset=PricingTier.objects.filter(expired=False),required=False,
        help_text=_('A pricing tier is required for online registration and payment. If your school handles scheduling, but not payment for lessons, then leave this blank.')
    )
    deleteSlot = forms.BooleanField(label=_('Delete slot'),initial=False,help_text=_('Note that only slots with no current bookings may be deleted at this time.'),required=False)
