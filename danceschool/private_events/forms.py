from django import forms
from django.forms import inlineformset_factory, widgets
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from django.db.models import Q

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Div, Submit
from crispy_forms.bootstrap import Accordion, AccordionGroup

from danceschool.core.models import EventOccurrence, Event
from danceschool.core.utils.timezone import ensure_timezone
from danceschool.core.forms import LocationWithDataWidget

from .models import PrivateEvent, EventReminder

EVENT_REPEAT_CHOICES = [
    (str(timedelta(hours=1).total_seconds()),_('Hour')),
    (str(timedelta(days=1).total_seconds()),_('Day'),),
    (str(timedelta(days=7).total_seconds()),_('Week')),
    ('months=+1',_('Month')),
    ('years=+1',_('Year')),
]

VISIBILITY_CHOICES = [
    ('all',_('All Staff')),
    ('me',_('Only To Me')),
    ('group',_('Select User Group')),
    ('users',_('Select Users')),
]

REMINDER_SET_CHOICES = [
    ('none',_('No One')),
    ('all',_('All Staff')),
    ('me',_('Only To Me')),
    ('group',_('Select User Group')),
    ('users',_('Select Users')),
]

REMINDER_TIME_CHOICES = [
    (0,_('0 minutes')),
    (30,_('30 minutes')),
    (60, _('1 hour')),
    (720,_('12 hours')),
    (4320, _('3 days')),
]


class AddPrivateEventForm(forms.ModelForm):

    visibleTo = forms.ChoiceField(label=_('Make this event visible to:'),choices=VISIBILITY_CHOICES,initial='all')

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)

        if user:
            kwargs.update(initial={
                'displayToUsers': [user.id,],
                'submissionUser': user.id,
            })

        super(AddPrivateEventForm,self).__init__(*args,**kwargs)
        self.fields['submissionUser'].widget = forms.HiddenInput()
        self.fields['status'].widget = forms.HiddenInput()
        self.fields['status'].initial = Event.RegStatus.hidden
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = False  # Our template must explicitly include the <form tag>
        self.helper.layout = Layout(
            'status',
            'submissionUser',
            'title',
            Div(
                Field('category', wrapper_class='col'),
                Field('visibleTo', wrapper_class='col'),
                css_class='form-row'),
            Div('displayToUsers'),
            Div('displayToGroup'),
            Accordion(
                AccordionGroup(_('Add A Description'),'descriptionField',active=False),
                AccordionGroup(_('Add A Location'),Div('location','room','locationString')),
                AccordionGroup(_('Add a Link'),'link'),
            ),
        )

    def clean(self):
        super(AddPrivateEventForm,self).clean()
        visibleTo = self.cleaned_data.get('visibleTo')
        submissionUser = self.cleaned_data.get('submissionUser')

        # Set visibility based on the choice the user made
        if visibleTo == 'all':
            self.cleaned_data.pop('displayToUsers',None)
            self.cleaned_data.pop('displayToGroup',None)
        elif visibleTo == 'me':
            self.cleaned_data['displayToUsers'] = [submissionUser,]
            self.cleaned_data.pop('displayToGroup',None)
        elif visibleTo == 'users':
            self.cleaned_data.pop('displayToGroup',None)
        elif visibleTo == 'group':
            self.cleaned_data.pop('displayToUsers',None)

    class Meta:
        model = PrivateEvent
        exclude = []
        widgets = {
            'location': LocationWithDataWidget,
        }

    class Media:
        js = ('timepicker/jquery.timepicker.min.js','jquery-ui/jquery-ui.min.js','moment/moment.min.js','js/addEvent_rollups.js','js/serieslocation_capacity_change.js',)
        css = {'all':('timepicker/jquery.timepicker.css','jquery-ui/jquery-ui.min.css',)}


class AddEventOccurrenceForm(forms.ModelForm):
    allDay = forms.BooleanField(label=_('All Day'),required=False)

    def clean(self):
        startTime = self.cleaned_data['startTime']
        endTime = self.cleaned_data['endTime']
        allDay = self.cleaned_data.pop('allDay', None) or False
        if allDay:
            self.cleaned_data['startTime'] = ensure_timezone(datetime(startTime.year,startTime.month,startTime.day))
            self.cleaned_data['endTime'] = ensure_timezone(datetime(endTime.year,endTime.month,endTime.day)) + timedelta(days=1)
        if self.cleaned_data['endTime'] < self.cleaned_data['startTime']:
            raise ValidationError(_('End time cannot be before start time.'),code='invalid')

    class Meta:
        model = EventOccurrence
        exclude = []


class OccurrenceFormSetHelper(FormHelper):

    def __init__(self, *args, **kwargs):
        super(OccurrenceFormSetHelper, self).__init__(*args, **kwargs)

        self.form_tag = False  # Our template must explicitly include the <form tag>
        self.layout = Layout(
            Div(
                Field('startTime', wrapper_class='col',),
                Field('endTime', wrapper_class='col',),
                Field('allDay', wrapper_class='col',),
                css_class='form-row'
            ),
            Div(
                Field('extraOccurrencesToAdd', wrapper_class='col',),
                Field('extraOccurrenceRule', wrapper_class='col',),
                css_class="form-row"
            ),
            Div(
                Field('sendReminderTo', wrapper_class='col',),
                Field('sendReminderWhen', wrapper_class='col',),
                Field('sendReminderWhich', wrapper_class='col',),
                css_class="form-row"
            ),
            Div('sendReminderGroup'),
            Div('sendReminderUsers'),
            Submit('submit', u'Submit', css_class='btn btn-primary'),
        )


class EventOccurrenceCustomFormSet(forms.BaseInlineFormSet):
    ''' Formset for occurrences added via the Private Events form '''

    def add_fields(self, form, index):
        super(EventOccurrenceCustomFormSet,self).add_fields(form,index)
        form.fields['startTime'] = forms.SplitDateTimeField(label=_("Start Time"),input_time_formats=['%I:%M%p','%-I:%M%p'], widget=widgets.SplitDateTimeWidget)
        form.fields['endTime'] = forms.SplitDateTimeField(label=_("End Time"),input_time_formats=['%I:%M%p','%-I:%M%p'], widget=widgets.SplitDateTimeWidget)
        form.fields['extraOccurrencesToAdd'] = forms.IntegerField(label=_("Repeat __ times:"),initial=0,min_value=0,max_value=100,required=False)
        form.fields['extraOccurrenceRule'] = forms.ChoiceField(label=_("Every:"),choices=EVENT_REPEAT_CHOICES,required=False)
        form.fields['sendReminderTo'] = forms.ChoiceField(label=_("Send A Reminder To:"),choices=REMINDER_SET_CHOICES,initial='none',required=False)
        form.fields['sendReminderWhen'] = forms.ChoiceField(label=_("Before:"),choices=REMINDER_TIME_CHOICES,initial=0,required=False)
        form.fields['sendReminderWhich'] = forms.ChoiceField(label=_("Ahead Of:"),choices=(('all',_('All Occurrences')),('first',_('First Occurrence Only'))),initial='all',required=False)
        form.fields['sendReminderGroup'] = forms.ModelChoiceField(label=_("Remind Group:"),queryset=Group.objects.all(),required=False)
        form.fields['sendReminderUsers'] = forms.ModelMultipleChoiceField(label=_("Remind Users:"),queryset=User.objects.filter(staffmember__isnull=False),required=False)

    def setReminder(self,occurrence):
        '''
        This function is called to create the actual reminders for each occurrence that is created.
        '''
        sendReminderTo = self[0].cleaned_data['sendReminderTo']
        sendReminderWhen = self[0].cleaned_data['sendReminderWhen']
        sendReminderGroup = self[0].cleaned_data['sendReminderGroup']
        sendReminderUsers = self[0].cleaned_data['sendReminderUsers']

        # Set the new reminder's time
        new_reminder_time = occurrence.startTime - timedelta(minutes=int(float(sendReminderWhen)))
        new_reminder = EventReminder(eventOccurrence=occurrence,time=new_reminder_time)
        new_reminder.save()

        # Set reminders based on the choice the user made
        if sendReminderTo == 'all':
            user_set = User.objects.filter(Q(staffmember__isnull=False) | Q(is_staff=True))
        elif sendReminderTo == 'me':
            user_set = User.objects.filter(id=occurrence.event.submissionUser.id)
        elif sendReminderTo == 'users':
            user_set = User.objects.filter(**{'id__in': sendReminderUsers})
        elif sendReminderTo == 'group':
            user_set = User.objects.filter(**{'groups': sendReminderGroup})
        else:
            user_set = []

        for user in user_set:
            new_reminder.notifyList.add(user)

    def save(self):
        extraOccurrencesToAdd = self[0].cleaned_data['extraOccurrencesToAdd']
        extraOccurrenceRule = self[0].cleaned_data['extraOccurrenceRule']
        sendReminderTo = self[0].cleaned_data['sendReminderTo']
        sendReminderWhich = self[0].cleaned_data['sendReminderWhich']

        # Save this actual occurrence first
        this_occurrence = super(EventOccurrenceCustomFormSet, self).save()

        # Create a reminder for this occurrence if applicable
        if sendReminderTo in ['all','me','users','group']:
            self.setReminder(this_occurrence[0])

        # Create new occurrences based on the number of occurrences to add and the occurrence rule given
        remainingOccurrences = extraOccurrencesToAdd

        # These will be repopulated with each loop and used to calculate the next event times
        old_startTime = this_occurrence[0].startTime
        old_endTime = this_occurrence[0].endTime

        # Make a new occurrence for each requested new occurrence.  Also, make a reminder if requested
        while remainingOccurrences > 0:
            if 'months' not in extraOccurrenceRule and 'years' not in extraOccurrenceRule:
                time_diff = timedelta(seconds=float(extraOccurrenceRule))
                new_startTime = old_startTime + time_diff
                new_endTime = old_endTime + time_diff
            elif 'months' in extraOccurrenceRule:
                num_months = int(float(extraOccurrenceRule.replace('months=','')))
                new_startTime = old_startTime + relativedelta(months=num_months)
                new_endTime = old_endTime + relativedelta(months=num_months)
            elif 'years' in extraOccurrenceRule:
                num_years = int(float(extraOccurrenceRule.replace('years=','')))
                new_startTime = old_startTime + relativedelta(years=num_years)
                new_endTime = old_endTime + relativedelta(years=num_years)

            # Create the occurrence
            new_occ = EventOccurrence(event=this_occurrence[0].event, startTime=new_startTime,endTime=new_endTime)
            new_occ.save()

            # Create the reminders
            if sendReminderWhich == 'all' and sendReminderTo in ['all','me','users','group']:
                self.setReminder(new_occ)

            # Finally, prepare for the next iteration of the loop
            old_startTime = new_startTime
            old_endTime = new_endTime
            remainingOccurrences -= 1


EventOccurrenceFormSet = inlineformset_factory(
    PrivateEvent, EventOccurrence,
    formset=EventOccurrenceCustomFormSet,
    form=AddEventOccurrenceForm,
    exclude=[],
    extra=1, can_delete=False
)
