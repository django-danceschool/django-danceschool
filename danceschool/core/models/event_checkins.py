from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
import logging

from .event_base import Event
from .event_occurrences import EventOccurrence
from .event_registration import EventRegistration

logger = logging.getLogger(__name__)


class EventCheckIn(models.Model):
    '''
    For attendance purposes, an individual can be checked into an event or into
    an event occurrence.  An individual is typically an event registrant, in
    which case this check-in is linked to the EventRegistration.  However, a
    check in may also contain only a name.  Database constraints exist to ensure
    that a person will not be checked into the same event or event occurrence
    more than once.
    '''

    CHECKIN_TYPE_CHOICES = [
        ('E', _('Event')),
        ('O', _('Event occurrence')),
    ]

    event = models.ForeignKey(
        Event, verbose_name=_('Event'), on_delete=models.CASCADE,
    )
    occurrence = models.ForeignKey(
        EventOccurrence, verbose_name=_('Event occurrence'),
        null=True, blank=True, on_delete=models.SET_NULL,
    )

    checkInType = models.CharField(
        _('Check-in type'), max_length=1, choices=CHECKIN_TYPE_CHOICES,
    )

    eventRegistration = models.ForeignKey(
        EventRegistration, verbose_name=_('Event registration'),
        null=True, blank=True, on_delete=models.SET_NULL
    )
    firstName = models.CharField(_('First name'), max_length=100, null=True)
    lastName = models.CharField(_('Last name'), max_length=100, null=True)

    cancelled = models.BooleanField(
        _('Check-in cancelled'), default=False, null=True, blank=True,
    )

    data = models.JSONField(_('Additional data'), default=dict, blank=True)

    creationDate = models.DateTimeField(
        _('Creation date'), auto_now_add=True
    )
    modifiedDate = models.DateTimeField(
        _('Last modified'), auto_now=True
    )

    # For keeping track of who submitted and when.
    submissionUser = models.ForeignKey(
        User, verbose_name=_('Submission User'), null=True,
        on_delete=models.SET_NULL
    )

    @property
    def fullName(self):
        return ' '.join([self.firstName or '', self.lastName or ''])
    fullName.fget.short_description = _('Name')

    def __str__(self):
        if self.checkInType == 'O':
            return '{}: {}'.format(self.fullName, self.occurrence.__str__())
        return '{}: {}'.format(self.fullName, self.event.name)

    class Meta:
        verbose_name = _('Event check-in')
        verbose_name_plural = _('Event check-ins')
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'eventRegistration'],
                condition=Q(
                    Q(checkInType='E') & Q(eventRegistration__isnull=False)
                ),
                name='unique_event_eventreg_checkin'
            ),
            models.UniqueConstraint(
                fields=['event', 'occurrence', 'eventRegistration'],
                condition=Q(
                    Q(checkInType='O') &
                    Q(occurrence__isnull=False) &
                    Q(eventRegistration__isnull=False)
                ),
                name='unique_occurrence_eventreg_checkin'
            ),
            models.UniqueConstraint(
                fields=['event', 'firstName', 'lastName'],
                condition=Q(
                    Q(checkInType='E') &
                    Q(eventRegistration__isnull=True) &
                    Q(firstName__isnull=False) &
                    Q(lastName__isnull=False)
                ),
                name='unique_event_name_checkin'
            ),
            models.UniqueConstraint(
                fields=['event', 'occurrence', 'firstName', 'lastName'],
                condition=Q(
                    Q(checkInType='O') &
                    Q(occurrence__isnull=False) &
                    Q(eventRegistration__isnull=True) &
                    Q(firstName__isnull=False) &
                    Q(lastName__isnull=False)
                ),
                name='unique_occurrence_name_checkin'
            )
        ]
