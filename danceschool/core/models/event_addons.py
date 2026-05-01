from django.db import models
from django.db.models import Q, F
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
import logging

from .event_base import Event

logger = logging.getLogger(__name__)


class EventAddOn(models.Model):
    '''
    An event add-on is a rule that indicates that a registration for a
    particular event will also automatically include registration for one or
    more additional events. The add-on also includes an allocation rule for net
    revenue associated for registration to this event, which may in the form of
    a fixed amount of revenue allocation, a defined percentage of the total
    revenue allocation, or a residual revenue allocation based on the prices
    of the individual add-on components. Event add-ons are designed for all-in
    passes and similar functionality, where registering for a single event
    (the all-in pass) should actually be signing one up for multiple events
    simultaneously. Using add-ons not only ensures that revenue is allocated as
    desired, it ensures that check-in capabilities for individual events are
    preserved, and that capacity restrictions may remain enforceable, etc.
    '''

    # Choices of Discount Types
    class AllocationType(models.TextChoices):
        fixed = ('F', _('Fixed dollar allocation'))
        percent = ('P', _('Fixed percentage allocation'))
        residual = ('R', _('Allocation based on individual event default prices'))

    event = models.ForeignKey(
        Event, verbose_name=_('Event'), on_delete=models.CASCADE
    )

    addOnEvent = models.ForeignKey(
        Event, verbose_name=_('Event'), on_delete=models.CASCADE,
        related_name='addon_of',
    )

    order = models.PositiveIntegerField(default=0, blank=False, null=False)

    allocationType = models.CharField(
        _('Revenue allocation type'), max_length=1,
        help_text=_(
            'How is registration revenue allocated to this event?'
        ),
        choices=AllocationType.choices, default=AllocationType.fixed
    )

    allocationAmount = models.FloatField(
        _('Allocation amount'),
        null=True, blank=True, default=0, validators=[MinValueValidator(0)],
        help_text=_(
            'Enter the fixed amount or percentage (out of 100) of revenue that '
            'will be allocated to this event. This field is ignored if '
            'allocation is based on event default prices.'
        )
    )

    def __str__(self):
        return _(f'Add-on for event %s: %s') % (self.event.name, self.addOnEvent.name)

    class Meta:
        ordering = ('order',)
        verbose_name = _('Event add-on')
        verbose_name_plural = _('Event add-ons')

        constraints = [
            models.UniqueConstraint(
                fields=['event', 'addOnEvent'],
                name='unique_addon_per_event',
            ),
            models.CheckConstraint(
                check=~Q(addOnEvent=F('event')),
                name='no_self_addons',
            )
        ]
