from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import logging

from .event_base import Event

logger = logging.getLogger(__name__)


class DanceRole(models.Model):
    '''
    Most typically for partnered dances, this will be only Lead and Follow.
    However, it can be generalized to other roles readily, or roles can be
    effectively disabled by simply creating a single role such as "Student."
    '''

    name = models.CharField(_('Name'), max_length=50, unique=True)
    pluralName = models.CharField(
        _('Plural of name'), max_length=50, unique=True,
        help_text=_('For the registration form.')
    )
    order = models.FloatField(
        _('Order number'),
        help_text=_('Lower numbers show up first when registering.')
    )

    def save(self, *args, **kwargs):
        ''' Just add "s" if no plural name given. '''

        if not self.pluralName:
            self.pluralName = self.name + 's'

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Dance role')
        verbose_name_plural = _('Dance roles')
        ordering = ('order',)


class EventRole(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    role = models.ForeignKey(DanceRole, on_delete=models.CASCADE)
    capacity = models.PositiveIntegerField()

    @property
    def sku(self):
        return f'EVENT_{self.event.id}_ROLE_{self.role_id}'

    def price(self, payAtDoor):
        return self.event.getBasePrice(payAtDoor=payAtDoor)

    def numRegistered(self, includeTemporaryRegs=False):
        '''
        Accepts a DanceRole object and returns the number of registrations of that role.
        '''
        filters = Q(cancelled=False) & Q(dropIn=False) & Q(role=self.role)
        excludes = Q()

        if includeTemporaryRegs:
            excludes = Q(registration__final=False) & Q(registration__invoice__expirationDate__lte=timezone.now())
        else:
            filters = filters & Q(registration__final=True)
        return self.event.eventregistration_set.filter(filters).exclude(excludes).count()

    class Meta:
        ''' Ensure each role is only listed once per event. '''
        unique_together = ('event', 'role')
        verbose_name = _('Event dance role')
        verbose_name_plural = _('Event dance roles')
