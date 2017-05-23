from django import forms
from django.utils.translation import ugettext_lazy as _

from danceschool.core.constants import getConstant
from danceschool.core.models import DanceRole, Location, Instructor

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
    role = forms.ChoiceField(label=_('Dance role'),choices=[(x.name, x) for x in DanceRole.objects.all()])
    participants = forms.IntegerField(label=_('Expected # Participants'),initial=1, min_value=1, help_text=_('Be advised that group lessons may be charged a different rate.'))
    comments = forms.CharField(label=_('Comments/Notes'), required=False, help_text=_('Please enter any comments or notes that you would like to be provided to the instructor before the lesson, such as the topics on which you may want to focus.'))


class SlotCreationForm(forms.Form):
    instructorId = forms.ModelChoiceField(label=_('Instructor'),queryset=Instructor.objects.all(),widget=forms.HiddenInput,required=True)

    startDate = forms.DateField(label=_('Start date'),required=True,widget=forms.HiddenInput)
    endDate = forms.DateField(label=_('End date'),required=True,widget=forms.HiddenInput)
    startTime = forms.TimeField(label=_('Start time'),required=True)
    endTime = forms.TimeField(label=_('End time'),required=True)

    location = forms.ModelChoiceField(label=_('Location'),queryset=Location.objects.exclude(status=Location.StatusChoices.former),required=False)
    status = forms.ChoiceField(label=_('Initial Status'),required=True,choices=InstructorAvailabilitySlot.SlotStatus.choices, initial=InstructorAvailabilitySlot.SlotStatus.available)


class SlotUpdateForm(forms.Form):
    slotIds = forms.ModelMultipleChoiceField(required=True,widget=forms.MultipleHiddenInput,queryset=InstructorAvailabilitySlot.objects.all())

    updateStatus = forms.ChoiceField(label=_('Update Status'),required=True,choices=InstructorAvailabilitySlot.SlotStatus.choices, initial=InstructorAvailabilitySlot.SlotStatus.available)
    updateLocation = forms.ModelChoiceField(label=_('Update Location'),queryset=Location.objects.exclude(status=Location.StatusChoices.former),required=False)
    deleteSlot = forms.BooleanField(label=_('Delete slot'),initial=False,help_text=_('Note that only slots with no current bookings may be deleted at this time.'),required=False)
