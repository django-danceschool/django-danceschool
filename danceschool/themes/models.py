from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils.html import strip_tags
from django.core.validators import MaxValueValidator

import os
from functools import partial

from cms.models.pluginmodel import CMSPlugin
from djangocms_text_ckeditor.fields import HTMLField
from djangocms_link.models import AbstractLink
from filer.fields.image import FilerImageField

from .constants import CAROUSEL_ASPECT_RATIO_CHOICES, CAROUSEL_PAUSE_CHOICES, CAROUSEL_RIDE_CHOICES, DEVICE_SIZES, GRID_COLUMN_CHOICES, GRID_SIZE


class SimpleBootstrapCardModel(CMSPlugin):
    '''
    This plugin model allows for easy creation of cards that fit into standard themes.
    For more sophisticated functionality, you may need to use custom HTML instead.
    '''

    template = models.CharField(_('Card template'),max_length=250,null=True,blank=True)

    cardPicture = FilerImageField(
        verbose_name=_('Header Picture'),blank=True,null=True,related_name='card_picture',
        help_text=_('If set, this picture goes at the top of the card, and it is scaled to the width of the card.'))
    body = HTMLField(verbose_name=_('Body content'),null=True,blank=True)
    footer = HTMLField(verbose_name=_('Footer content'),null=True,blank=True,help_text=_('Optional'))

    def __str__(self):
        return str(self.pk)

    def get_short_description(self):
        text = 'Bootstrap Card #{}'.format(self.pk)
        return text


class BootstrapRowModel(CMSPlugin):
    '''
    This plugin model allows for creation of Bootstrap rows for easy grid construction.
    '''

    template = models.CharField(_('Row template'),max_length=250,null=True,blank=True)

    def __str__(self):
        return str(self.pk)

    def get_short_description(self):
        text = 'Bootstrap Grid Row #{}'.format(self.pk)
        return text


class BootstrapColumnModel(CMSPlugin):
    '''
    This plugin model allows for creation of Bootstrap columns, which can
    be embedded within rows for easy grid construction.
    '''

    template = models.CharField(_('Column template'),max_length=250,null=True,blank=True)

    column_type = models.CharField(
        verbose_name=_('Column type'),
        choices=GRID_COLUMN_CHOICES,
        default=GRID_COLUMN_CHOICES[0][0],
        blank=True,
        max_length=255,
    )
    column_size = models.PositiveSmallIntegerField(
        verbose_name=_('Column size'),
        blank=True,
        null=True,
        validators=[MaxValueValidator(GRID_SIZE)],
        help_text=_(
            'Numeric value from 1 - {bound}. '
            'Spreads the columns evenly when empty.').format(bound=GRID_SIZE)
    )

    def __str__(self):
        return str(self.pk)

    def get_short_description(self):
        text = ''
        classes = self.get_grid_values()
        if self.column_size:
            text += '(col-{}) '.format(self.column_size)
        else:
            text += '(auto) '
        if self.column_type != 'col':
            text += '.{} '.format(self.column_type)
        if classes:
            text += '.{}'.format(' .'.join(self.get_grid_values()))
        return text

    def get_grid_values(self):
        classes = []
        for device in DEVICE_SIZES:
            for element in ('col', 'order', 'ml', 'mr'):
                size = getattr(self, '{}_{}'.format(device, element))
                if size and (element == 'col' or element == 'order'):
                    classes.append('{}-{}-{}'.format(element, device, int(size)))
                elif size:
                    classes.append('{}-{}-{}'.format(element, device, 'auto'))
        return classes


class BootstrapCarousel(CMSPlugin):
    """
    Components > "Carousel" Plugin
    https://getbootstrap.com/docs/4.0/components/carousel/
    """
    template = models.CharField(_('Carousel template'),max_length=250,null=True,blank=True)

    carousel_interval = models.IntegerField(
        verbose_name=_('Interval'),
        default=5000,
        help_text=_('The amount of time to delay between automatically cycling '
                    'an item. If false, carousel will not automatically cycle.'),
    )
    carousel_controls = models.BooleanField(
        verbose_name=_('Controls'),
        default=True,
        help_text=_('Adding in the previous and next controls.'),
    )
    carousel_indicators = models.BooleanField(
        verbose_name=_('Indicators'),
        default=True,
        help_text=_('Adding in the indicators to the carousel.'),
    )
    carousel_keyboard = models.BooleanField(
        verbose_name=_('Keyboard'),
        default=True,
        help_text=_('Whether the carousel should react to keyboard events.'),
    )
    carousel_pause = models.CharField(
        verbose_name=_('Pause'),
        choices=CAROUSEL_PAUSE_CHOICES,
        default=CAROUSEL_PAUSE_CHOICES[0][0],
        max_length=255,
        help_text=_('If set to "hover", pauses the cycling of the carousel on '
                    '"mouseenter" and resumes the cycling of the carousel on '
                    '"mouseleave". If set to "false", hovering over the carousel '
                    'won\'t pause it.')
    )
    carousel_ride = models.CharField(
        verbose_name=_('Ride'),
        choices=CAROUSEL_RIDE_CHOICES,
        default=CAROUSEL_RIDE_CHOICES[0][0],
        max_length=255,
        help_text=_('Autoplays the carousel after the user manually cycles the '
                    'first item. If "carousel", autoplays the carousel on load.'),
    )
    carousel_wrap = models.BooleanField(
        verbose_name=_('Wrap'),
        default=True,
        help_text=_('Whether the carousel should cycle continuously or have '
                    'hard stops.'),
    )
    carousel_aspect_ratio = models.CharField(
        verbose_name=_('Aspect ratio'),
        choices=CAROUSEL_ASPECT_RATIO_CHOICES,
        blank=True,
        default='',
        max_length=255,
        help_text=_('Determines width and height of the image '
                    'according to the selected ratio.'),
    )

    def __str__(self):
        return str(self.pk)

    def get_short_description(self):
        text = _('(Carousel #{}').format(self.pk)
        text += ' ' + _('Interval: {}').format(self.carousel_interval)
        text += ', ' + _('Controls: {}').format(self.carousel_controls)
        text += ', ' + _('Indicators: {}').format(self.carousel_indicators)
        text += ', ' + _('Keyboard: {}').format(self.carousel_keyboard)
        text += ', ' + _('Pause: {}').format(self.carousel_pause)
        text += ', ' + _('Ride: {}').format(self.carousel_ride)
        text += _('Wrap: {}').format(self.carousel_wrap)
        return text


class BootstrapCarouselSlide(AbstractLink, CMSPlugin):
    carousel_image = FilerImageField(
        verbose_name=_('Slide image'),
        blank=False,
        null=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    carousel_content = HTMLField(
        verbose_name=_('Content'),
        blank=True,
        default='',
        help_text=_('Content may also be added using child plugins.'),
    )

    def __str__(self):
        return str(self.pk)

    def clean(self):
        super(AbstractLink, self).clean()

    def get_link(self):
        return AbstractLink.get_link(self)

    def get_short_description(self):
        image_text = content_text = ''

        if self.carousel_image_id:
            if self.carousel_image.name:
                image_text = self.carousel_image.name
            elif self.carousel_image.original_filename \
                    and os.path.split(self.carousel_image.original_filename)[1]:
                image_text = os.path.split(self.carousel_image.original_filename)[1]
            else:
                image_text = 'Image'
        if self.carousel_content:
            text = strip_tags(self.carousel_content).strip()
            if len(text) > 100:
                content_text = '{}...'.format(text[:100])
            else:
                content_text = '{}'.format(text)

        if image_text and content_text:
            return '{} ({})'.format(image_text, content_text)
        else:
            return image_text or content_text


IntegerFieldPartial = partial(
    models.PositiveSmallIntegerField,
    blank=True,
    null=True,
    validators=[MaxValueValidator(12)],
)

BooleanFieldPartial = partial(
    models.BooleanField,
    default=False,
)

# Loop through Bootstrap 4 device choices and generate
# model fields to cover col-*, order-*
for size in DEVICE_SIZES:
    # Grid size
    BootstrapColumnModel.add_to_class(
        '{}_col'.format(size),
        IntegerFieldPartial(),
    )
    # Grid ordering
    BootstrapColumnModel.add_to_class(
        '{}_order'.format(size),
        IntegerFieldPartial(),
    )
    # Grid margin left (ml)
    BootstrapColumnModel.add_to_class(
        '{}_ml'.format(size),
        BooleanFieldPartial(),
    )
    # Grid margin right (ml)
    BootstrapColumnModel.add_to_class(
        '{}_mr'.format(size),
        BooleanFieldPartial(),
    )

    def __str__(self):
        return str(self.pk)

    def get_short_description(self):
        text = 'Bootstrap Grid Column #{}'.format(self.pk)
        return text
