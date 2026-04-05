from django.db import models
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from djangocms_text_ckeditor.fields import HTMLField
from calendar import month_name
import logging

from ..constants import getConstant
from .event_base import Event
from .event_features import ClassDescription, get_defaultSeriesPageTemplate
from .event_categories import SeriesCategory, PublicEventCategory
from .event_prices import PricingTier
from .staff import StaffMember, EventStaffMember

logger = logging.getLogger(__name__)


def get_defaultPublicEventPageTemplate():
    ''' Callable for default used by PublicEvent class '''
    return (
        getConstant('general__defaultPublicEventPageTemplate') or
        'core/event_pages/individual_event.html'
    )


class Series(Event):
    '''
    A series is a particular type (subclass) of event which has instructors
    (a subclass of staff).  Series are also matched to a ClassDescription,
    through which their DanceType and DanceTypeLevel are specified.
    '''

    classDescription = models.ForeignKey(
        ClassDescription, verbose_name=_('Class description'), null=True,
        on_delete=models.SET_NULL
    )
    category = models.ForeignKey(
        SeriesCategory, verbose_name=_('Series category (optional)'),
        null=True, blank=True,
        help_text=_(
            'Custom series categories may be used to display special series ' +
            '(e.g. one-offs, visiting instructors) separately on your registration page.'
        ),
        on_delete=models.SET_NULL
    )
    allowDropins = models.BooleanField(
        _('Allow class drop-ins'), default=False,
        help_text=_('If checked, then all staff will be able to register students as drop-ins.')
    )

    def getTeachers(self, includeSubstitutes=False):
        staff_categories = [
            getConstant('general__eventStaffCategoryInstructor')
        ]
        if includeSubstitutes:
            staff_categories.append(
                getConstant('general__eventStaffCategorySubstitute')
            )

        return StaffMember.objects.filter(
            eventstaffmember__event=self,
            eventstaffmember__category__in=staff_categories
        ).distinct()

    teachers = property(fget=getTeachers)
    teachers.fget.short_description = _('Instructors')

    pricingTier = models.ForeignKey(
        PricingTier, verbose_name=_('Pricing tier'), on_delete=models.PROTECT
    )

    @property
    def name(self):
        '''
        Overrides property from Event base class.
        '''
        return getattr(getattr(self, 'classDescription', None), 'title', '')
    name.fget.short_description = _('Name')

    @property
    def description(self):
        '''
        Overrides property from Event base class.
        '''
        return getattr(getattr(self, 'classDescription', None), 'description', '')
    description.fget.short_description = _('Description')

    @property
    def shortDescription(self):
        '''
        Overrides property from Event base class.
        '''
        cd = getattr(self, 'classDescription', None)
        if cd:
            sd = getattr(cd, 'shortDescription', '')
            d = getattr(cd, 'description', '')
            return sd if sd else d
        return ''
    shortDescription.fget.short_description = _('Short description')

    @property
    def slug(self):
        '''
        No property in the Event base class, but PublicEvents have a slug field,
        so this allows us to iterate over that property in templates
        '''
        return getattr(getattr(self, 'classDescription', None), 'slug', '')
    slug.fget.short_description = _('Slug')

    @property
    def template(self):
        ''' This just passes along the template from the associated ClassDescription. '''
        return getattr(
            getattr(self, 'classDescription', None), 'template',
            get_defaultSeriesPageTemplate()
        )
    template.fget.short_description = _('Template')

    @property
    def displayColor(self):
        '''
        Overrides property from Event base class.
        '''
        cd = getattr(self, 'classDescription', None)
        if cd:
            return cd.danceTypeLevel.displayColor
    displayColor.fget.short_description = _('Calendar display color')

    def getBasePrice(self, **kwargs):
        '''
        This method overrides the method of the base Event class by
        checking the pricingTier associated with this Series and getting
        the appropriate price for it.
        '''
        if not self.pricingTier:
            return 0
        return self.pricingTier.getBasePrice(**kwargs)

    # base price is the non-student, online registration price.
    basePrice = property(fget=getBasePrice)
    basePrice.fget.short_description = _('Base price for online registration')

    @property
    def url(self):
        orgRule = getConstant('registration__orgRule')

        if self.status in [self.RegStatus.hidden, self.RegStatus.linkOnly]:
            return None
        elif orgRule in [
            'SessionFirst', 'SessionAlphaFirst', 'SessionMonth', 'SessionAlphaMonth'
        ] and self.session:
            return reverse(
                'classViewSessionMonth',
                args=[
                    self.session.slug,
                    self.year,
                    month_name[self.month or 0] or None,
                    self.classDescription.slug
                ]
            )
        elif orgRule in ['Session', 'SessionAlpha'] and self.session:
            return reverse('classViewSession', args=[self.session.slug, self.classDescription.slug])
        else:
            return reverse(
                'classView', args=[
                    self.year,
                    month_name[self.month or 0] or None,
                    self.classDescription.slug
                ]
            )

    url.fget.short_description = _('Class series URL')

    def clean(self):
        if self.allowDropins and not self.pricingTier.dropinPrice:
            raise ValidationError(_(
                'If drop-ins are allowed then drop-in price must be specified by the Pricing Tier.'
            ))
        super().clean()

    def __str__(self):
        if self.month and self.year and self.classDescription:
            # In case of unsaved series, month and year are not yet set.
            return str(_('%s %s: %s' % (
                month_name[self.month or 0], str(self.year), self.classDescription.title
            )))
        elif self.classDescription:
            return str(_('Class Series: %s' % self.classDescription.title))
        else:
            return str(_('Class Series'))

    class Meta:
        verbose_name = _('Class series')
        verbose_name_plural = _('Class series')


class PublicEvent(Event):
    '''
    Special Events which may have their own display page.
    '''

    title = models.CharField(_('Title'), max_length=100, help_text=_('Give the event a title'))
    slug = models.SlugField(
        _('Slug'), max_length=100,
        help_text=_('This is for the event page URL, you can override the default.')
    )

    category = models.ForeignKey(
        PublicEventCategory, null=True, blank=True,
        verbose_name=_('Category (optional)'),
        help_text=_(
            'Custom event categories may be used to display special types of ' +
            'events (e.g. practice sessions) separately on your registration ' +
            'page.  They may also be displayed in different colors on the ' +
            'public calendar.'
        ),
        on_delete=models.SET_NULL
    )
    descriptionField = HTMLField(
        _('Description'), null=True, blank=True,
        help_text=_('Describe the event for the event page.')
    )
    shortDescriptionField = models.TextField(
        _('Short description'), null=True, blank=True,
        help_text=_('Shorter description for \"taglines\" and feeds.')
    )

    template = models.CharField(
        _('Template for automatically-generated event page'),
        max_length=250, default=get_defaultPublicEventPageTemplate
    )

    link = models.URLField(
        _('External link to event (if applicable)'), blank=True, null=True,
        help_text=_(
            'Optionally include the URL to a page for this Event.  If set, ' +
            'then the site\'s auto-generated Event page will instead redirect ' +
            'to this URL.'
        )
    )

    # The pricing tier is optional, but registrations cannot be enabled unless a
    # pricing tier is specified (the pricing tier may specify the price as free
    # for Free events).
    pricingTier = models.ForeignKey(
        PricingTier, null=True, blank=True, verbose_name=_('Pricing Tier'),
        on_delete=models.SET_NULL
    )

    def getBasePrice(self, **kwargs):
        '''
        This method overrides the method of the base Event class by
        checking the pricingTier associated with this PublicEvent and getting
        the appropriate price for it.
        '''
        if not self.pricingTier:
            return 0
        return self.pricingTier.getBasePrice(**kwargs)

    # The base price is the non-student, online registration price.
    basePrice = property(fget=getBasePrice)
    basePrice.fget.short_description = _('Base price for online registration')

    @property
    def djs(self):
        '''
        Returns the list of DJs
        '''
        return EventStaffMember.objects.filter(
            event=self,
            category=getConstant('general__eventStaffCategoryDJ')
        )
    djs.fget.short_description = _('DJs')

    @property
    def name(self):
        '''
        Overrides property from Event base class.
        '''
        return self.title
    name.fget.short_description = _('Name')

    @property
    def description(self):
        '''
        Overrides property from Event base class.
        '''
        return self.descriptionField
    description.fget.short_description = _('Description')

    @property
    def shortDescription(self):
        '''
        Overrides property from Event base class.
        '''
        if self.shortDescriptionField:
            return self.shortDescriptionField
        return self.descriptionField
    shortDescription.fget.short_description = _('Short description')

    @property
    def url(self):
        orgRule = getConstant('registration__orgRule')

        if self.status in [self.RegStatus.hidden, self.RegStatus.linkOnly]:
            return None
        elif orgRule in [
            'SessionFirst', 'SessionAlphaFirst', 'SessionMonth', 'SessionAlphaMonth'
        ] and self.session:
            return reverse(
                'eventViewSessionMonth', args=[
                    self.session.slug, self.year,
                    month_name[self.month or 0] or None, self.slug
                ]
            )
        elif orgRule in ['Session', 'SessionAlpha'] and self.session:
            return reverse('eventViewSession', args=[self.session.slug, self.slug])
        else:
            return reverse(
                'eventView',
                args=[self.year, month_name[self.month or 0] or None, self.slug]
            )

    def __str__(self):
        try:
            return '%s: %s' % (self.name, self.firstOccurrenceTime.strftime('%a., %B %d, %Y, %I:%M %p'))
        except AttributeError:
            # Event has no occurrences
            return self.name

    class Meta:
        verbose_name = _('Public event')
        verbose_name_plural = _('Public events')
