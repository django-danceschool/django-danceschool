from django.db import models
from django.utils.translation import gettext_lazy as _
from djangocms_text.fields import HTMLField
from colorful.fields import RGBColorField
import logging

from ..constants import getConstant
from .event_roles import DanceRole

logger = logging.getLogger(__name__)


def get_defaultClassColor():
    ''' Callable for default used by DanceTypeLevel class '''
    return getConstant('calendar__defaultClassColor')


def get_defaultSeriesPageTemplate():
    ''' Callable for default used by Series class '''
    return (
        getConstant('general__defaultSeriesPageTemplate') or
        'core/event_pages/individual_class.html'
    )


class DanceType(models.Model):
    '''
    Many dance studios will have only one dance type, but this allows the studio to
    run classes in multiple dance types with different roles for each (e.g. partnered
    vs. non-partnered dances).
    '''
    name = models.CharField(_('Name'), max_length=50, unique=True)
    order = models.FloatField(
        _('Order number'),
        help_text=_(
            'Lower numbers show up first when choosing class types in the ' +
            'admin.  By default, this does not affect ordering on ' +
            'public-facing registration pages.'
        )
    )

    roles = models.ManyToManyField(
        DanceRole, verbose_name=_('Dance roles'),
        help_text=_(
            'Select default roles used for registrations of this dance type ' +
            '(can be overriden for specific events).'
        )
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Dance type')
        verbose_name_plural = _('Dance types')
        ordering = ('order',)


class DanceTypeLevel(models.Model):
    '''
    Levels are defined within dance types.
    '''
    name = models.CharField(_('Name'), max_length=50)
    order = models.FloatField(
        _('Order number'), help_text=_('This is used to order and look up dance types.')
    )
    danceType = models.ForeignKey(
        DanceType, verbose_name=_('Dance Type'), on_delete=models.CASCADE
    )
    displayColor = RGBColorField(
        _('Display Color'),
        help_text=_('Choose a color for the calendar display.'),
        default=get_defaultClassColor
    )

    def __str__(self):
        return ' - '.join([self.danceType.name, self.name])

    class Meta:
        verbose_name = _('Level of dance type')
        verbose_name_plural = _('Levels of dance type')
        ordering = ('danceType__order', 'order',)


class ClassDescription(models.Model):
    '''
    All the classes we teach.
    '''
    title = models.CharField(_('Title'), max_length=200)
    description = HTMLField(_('Description'), blank=True)
    shortDescription = models.TextField(
        _('Short description'), blank=True,
        help_text=_('May be used for tag lines and feeds.')
    )
    danceTypeLevel = models.ForeignKey(
        DanceTypeLevel, verbose_name=_('Dance Type & Level'), default=1,
        on_delete=models.SET_DEFAULT
    )

    slug = models.SlugField(
        _('Slug'), max_length=100, unique=True, blank='True',
        help_text=_(
            'This is used in the URL for the individual class pages.  ' +
            'You can override the default'
        )
    )

    template = models.CharField(
        _('Template for automatically-generated class series page'),
        max_length=250, default=get_defaultSeriesPageTemplate
    )

    oneTimeSeries = models.BooleanField(
        _('One Time Series'), default=False,
        help_text=_(
            'If checked, this class description will not show up in the ' +
            'dropdown menu when creating a new series.'
        )
    )

    @property
    def danceTypeName(self):
        return self.danceTypeLevel.danceType.name
    danceTypeName.fget.short_description = _('Dance type')

    @property
    def levelName(self):
        return self.danceTypeLevel.name
    levelName.fget.short_description = _('Level')

    @property
    def lastOffered(self):
        '''
        Returns the start time of the last time this series was offered
        '''
        return getattr(self.series_set.order_by('-startTime').first(), 'startTime', None)
    lastOffered.fget.short_description = _('Last offered')

    @property
    def lastOfferedMonth(self):
        '''
        Sometimes a Series is associated with a month other than the one
        in which the first class begins, so this returns a (year, month) tuple
        that can be used in admin instead.
        '''
        lastOfferedSeries = self.series_set.order_by('-startTime').first()
        return (
            getattr(lastOfferedSeries, 'year', None),
            getattr(lastOfferedSeries, 'month', None)
        )
    lastOfferedMonth.fget.short_description = _('Last offered')

    def __str__(self):
        lastOffered = self.lastOffered
        if lastOffered:
            return '{} ({} {})'.format(
                self.title, _('Last offered'),
                lastOffered.strftime('%Y-%m-%d')
            )
        return self.title

    class Meta:
        '''
        Show descriptions of classes that were most recently offered first.
        '''
        ordering = ('-series__startTime',)
        verbose_name = _('Class series description')
        verbose_name_plural = _('Class series descriptions')
