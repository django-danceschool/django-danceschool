from django.db import models
from django.utils.translation import gettext_lazy as _
from colorful.fields import RGBColorField
import logging

from ..utils.timezone import ensure_localtime

logger = logging.getLogger(__name__)


class EventSession(models.Model):
    '''
    Event sessions can be used to group different types of events together both for
    registration purposes and for application of discounts/vouchers.  By default,
    sessions are ordered according to their start date, which is set automatically based
    on the events associated with the session.
    '''

    name = models.CharField(_('Name'), max_length=100, help_text=_('Session name will be displayed.'))
    description = models.TextField(
        _('Description'), null=True, blank=True, help_text=_('Add an optional description.')
    )
    slug = models.SlugField(
        _('Slug'),
        max_length=50,
        help_text=_(
            'Events can be accessed by a URL based on this slug, as well as by ' +
            'a URL specified by month.'
        ),
    )

    startTime = models.DateTimeField(
        _('Start Time'),
        help_text=_(
            'This value should be populated automatically based on the first ' +
            'start time of any event associated with this session.'
        ),
        null=True, blank=True,
    )
    endTime = models.DateTimeField(
        _('End Time'),
        help_text=_(
            'This value should be populated automatically based on the last end ' +
            'time of any event associated with this session.'
        ),
        null=True, blank=True,
    )

    @property
    def localStartTime(self):
        return ensure_localtime(self.startTime)

    @property
    def localEndTime(self):
        return ensure_localtime(self.endTime)

    def save(self, *args, **kwargs):
        logger.debug('Save method for EventSession called. Updating start and end times')

        # Update the start and end time variables based on associated events.
        events = self.event_set.all()
        if events:
            self.startTime = events.order_by('startTime').first().startTime
            self.endTime = events.order_by('endTime').last().endTime

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('startTime', 'name')
        verbose_name = _('Event session')
        verbose_name_plural = _('Event sessions')


class EventCategory(models.Model):
    '''
    This abstract base class defines the categorization schema used for
    both public and private events.  If new Events classes are created,
    then their categorization may also inherit from this class.
    '''

    name = models.CharField(
        _('Name'), max_length=100, unique=True,
        help_text=_('Category name will be displayed.')
    )
    description = models.TextField(
        _('Description'), null=True, blank=True,
        help_text=_('Add an optional description.')
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)
        verbose_name = _('Event category')
        verbose_name_plural = _('Event categories')
        abstract = True


class SeriesCategory(EventCategory):
    '''
    Categorization for class series events, inherits from EventCategory.
    '''
    slug = models.SlugField(
        _('Slug'), max_length=50,
        help_text=_(
            'This slug is used primarily for custom templates in registration, ' +
            'if the category is shown separately on the registration page.  ' +
            'You can override the default.'
        )
    )
    separateOnRegistrationPage = models.BooleanField(
        _('Show category separately on registration page'), default=False
    )

    class Meta:
        verbose_name = _('Series category')
        verbose_name_plural = _('Series categories')


class PublicEventCategory(EventCategory):
    '''
    Categorization for public events, inherits from EventCategory.
    '''
    slug = models.SlugField(
        _('Slug'), max_length=50,
        help_text=_(
            'This slug is used primarily for custom templates in registration, ' +
            'if the category is shown separately on the registration page.  ' +
            'You can override the default.'
        )
    )
    separateOnRegistrationPage = models.BooleanField(
        _('Show category separately on registration page'), default=False
    )
    displayColor = RGBColorField(_('Calendar display color'), default='#0000FF')

    class Meta:
        verbose_name = _('Public event category')
        verbose_name_plural = _('Public event categories')
