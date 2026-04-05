from django.db import models
from django.db.models import Q, F
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import datetime, timedelta
import logging

from ..utils.timezone import ensure_localtime
from .event_base import Event

logger = logging.getLogger(__name__)


class EventOccurrence(models.Model):
    '''
    All events have one or more occurrences.  For example, class series have classes,
    public events may be one time (one occurrence) or they may occur repeatedly.
    '''
    event = models.ForeignKey(Event, verbose_name=_('Series/Event'), on_delete=models.CASCADE)

    startTime = models.DateTimeField(_('Start Time'))
    endTime = models.DateTimeField(_('End Time'))

    cancelled = models.BooleanField(
        _('Cancelled'),
        help_text=_('Check this box to mark that the class or event was cancelled.'),
        default=False
    )

    @property
    def localStartTime(self):
        return ensure_localtime(self.startTime)

    @property
    def localEndTime(self):
        return ensure_localtime(self.endTime)

    @property
    def duration(self):
        '''
        Returns the duration, in hours, for this occurrence
        '''
        return (self.endTime - self.startTime).total_seconds() / 3600
    duration.fget.short_description = _('Duration')

    def allDayForDate(self, this_date, timeZone=None):
        '''
        This method determines whether the occurrence lasts the entirety of
        a specified day in the specified time zone.  If no time zone is specified,
        then it uses the default time zone).  Also, give a grace period of a few
        minutes to account for issues with the way events are sometimes entered.
        '''
        if isinstance(this_date, datetime):
            d = this_date.date()
        else:
            d = this_date

        date_start = datetime(d.year, d.month, d.day)
        naive_start = (
            self.startTime if timezone.is_naive(self.startTime) else
            timezone.make_naive(self.startTime, timezone=timeZone)
        )
        naive_end = (
            self.endTime if timezone.is_naive(self.endTime) else
            timezone.make_naive(self.endTime, timezone=timeZone)
        )

        return (
            # Ensure that all comparisons are done in local time
            naive_start <= date_start and
            naive_end >= date_start + timedelta(days=1, minutes=-30)
        )

    @property
    def timeDescription(self):
        startDate = self.localStartTime.date()
        endDate = self.localEndTime.date()

        # If all of one date, then just describe it as such
        if self.allDayForDate(startDate) and startDate == endDate:
            return _('On %s' % self.localStartTime.strftime('%A, %B %d'))

        # Otherwise, describe appropriately
        sameYear = (startDate.year == endDate.year)
        textStrings = []
        for d in [self.localStartTime, self.localEndTime]:
            if self.allDayForDate(d) and sameYear:
                textStrings.append(d.strftime('%A, %B %d'))
            elif self.allDayForDate(d):
                textStrings.append(d.strftime('%B %d %Y'))
            else:
                textStrings.append(d.strftime('%B %d, %Y, %-I:%M %p'))

        return _('From {startTime} to {endTime}'.format(
            startTime=textStrings[0], endTime=textStrings[1]
        ))
    timeDescription.fget.short_description = _('Occurs')

    def clean(self):
        if self.endTime < self.startTime:
            raise ValidationError(_('End time cannot occur before start time.'))

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.event.updateTimes()

    def delete(self, *args, **kwargs):
        event = self.event
        super().delete(*args, **kwargs)
        event.updateTimes()

    def __str__(self):
        return '%s: %s' % (self.event.name, self.timeDescription)

    class Meta:
        verbose_name = _('Event occurrence')
        verbose_name_plural = _('Event occurrences')
        ordering = ('event', 'startTime')
        constraints = [
            models.CheckConstraint(
                check=Q(endTime__gte=F('startTime')),
                name='%(app_label)s_%(class)s_correct_endTime'
            ),
        ]
