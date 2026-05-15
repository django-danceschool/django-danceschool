from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from djangocms_text.fields import HTMLField
import logging

from ..constants import getConstant

logger = logging.getLogger(__name__)


def get_defaultEventCapacity():
    ''' Callable for default used by Location class '''
    return getConstant('registration__defaultEventCapacity')


class Location(models.Model):
    '''
    Events are held at locations.
    '''
    class StatusChoices(models.TextChoices):
        active = ('A', _('Active Location'))
        former = ('F', _('Former Location'))
        specialEvents = ('S', _('Special Event Location (not shown by default)'))

    name = models.CharField(
        _('Name'), max_length=80, unique=True,
        help_text=_('Give this location a name.')
    )

    address = models.CharField(
        'Street address', max_length=50,
        help_text=_('Enter the location\'s street address.'),
        blank=True, null=True
    )
    city = models.CharField(_('City'), max_length=30, default='Cambridge')
    state = models.CharField(_('2-digit state code'), max_length=12, default='MA')
    zip = models.CharField(_('ZIP/postal code'), max_length=12, default='02138')

    directions = HTMLField(
        _('Directions'),
        help_text=_(
            'Insert any detailed directions that you would like here.  ' +
            'Use HTML to include videos, formatting, etc.'
        ),
        null=True, blank=True
    )

    # This property restricts the visibility of the location in dropdowns
    # and on the publicly presented list of locations
    status = models.CharField(
        _('Status'), max_length=1,
        help_text=_('Is this location used regularly, used for special events, or no longer used?'),
        choices=StatusChoices.choices, default=StatusChoices.active
    )

    orderNum = models.FloatField(
        _('Order number'), default=0,
        help_text=_('This determines the order that the locations show up on the Locations page.')
    )

    defaultCapacity = models.PositiveIntegerField(
        _('Default Venue Capacity'), null=True, blank=True,
        default=get_defaultEventCapacity,
        help_text=_('If set, this will be used to determine capacity for class series in this venue.')
    )

    @property
    def address_string(self):
        commasep_fields = [self.address, self.city, self.state]
        return ' '.join([
            ', '.join([x for x in commasep_fields if x]),
            self.zip
        ])
    address_string.fget.short_description = _('Address')

    @property
    def address_string_multiline(self):
        retval = ''

        if self.address:
            retval += f'{self.address}\n'
        commasep_fields = [self.city, self.state]
        retval += ' '.join([
            ', '.join([x for x in commasep_fields if x]),
            self.zip
        ])
        return retval
    address_string_multiline.fget.short_description = _('Address')

    @property
    def jsonCalendarFeed(self):
        '''
        Allows for easy viewing of location-specific calendar feeds.
        '''
        return reverse('jsonCalendarLocationFeed', args=(self.id,))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Location')
        verbose_name_plural = _('Locations')
        ordering = ('orderNum',)


class Room(models.Model):
    '''
    Locations may have multiple rooms, each of which may have its own capacity.
    '''
    name = models.CharField(_('Name'), max_length=80, help_text=_('Give this room a name.'))
    location = models.ForeignKey(Location, verbose_name=_('Location'), on_delete=models.CASCADE)

    defaultCapacity = models.PositiveIntegerField(
        _('Default Venue Capacity'), null=True, blank=True,
        default=get_defaultEventCapacity,
        help_text=_('If set, this will be used to determine capacity for class series in this room.')
    )

    description = HTMLField(
        _('Description'),
        help_text=_(
            'By default, only room names are listed publicly.  However, you ' +
            'may insert any descriptive information that you would like about ' +
            'this room here.'
        ),
        null=True, blank=True
    )

    @property
    def jsonCalendarFeed(self):
        '''
        Allows for easy viewing of room-specific calendar feeds.
        '''
        return reverse('jsonCalendarLocationFeed', args=(self.location.id, self.id,))

    def __str__(self):
        return self.name

    class Meta:
        unique_together = ('location', 'name')
        verbose_name = _('Room')
        verbose_name_plural = _('Rooms')
        ordering = ('location__name', 'name',)
