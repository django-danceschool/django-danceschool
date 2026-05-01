from django.contrib import admin
from django.forms import ModelForm, SplitDateTimeField
from django.utils.translation import gettext_lazy as _

from ..models import EventOccurrence, EventStaffMember
from .event_base import WIDGET_FORMATS


class EventOccurrenceInlineForm(ModelForm):
    startTime = SplitDateTimeField(
        required=True, label=_('Start Date/Time'), input_time_formats=WIDGET_FORMATS
    )
    endTime = SplitDateTimeField(
        required=True, label=_('End Date/Time'), input_time_formats=WIDGET_FORMATS
    )


class EventOccurrenceInline(admin.TabularInline):
    model = EventOccurrence
    form = EventOccurrenceInlineForm
    extra = 1

    class Media:
        js = (
            'https://cdn.jsdelivr.net/npm/moment@2.30.1/moment.min.js',
            'https://cdn.jsdelivr.net/npm/datepair.js@0.4.17/dist/jquery.datepair.min.js',
            'js/eventadmin_pickers.js'
        )
