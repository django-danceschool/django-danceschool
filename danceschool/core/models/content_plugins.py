from django.db import models
from django.utils.translation import gettext_lazy as _
from calendar import day_name

from filer.models import ThumbnailOption
from multiselectfield import MultiSelectField
from cms.models.pluginmodel import CMSPlugin
import logging

from .staff import StaffMember, Instructor
from .locations import Location
from .event_categories import PublicEventCategory, SeriesCategory
from .event_features import DanceTypeLevel

logger = logging.getLogger(__name__)


class StaffMemberPluginModel(CMSPlugin):
    ''' Views on an individual staff member or instructor use this model for configuration. '''
    staffMember = models.ForeignKey(
        StaffMember, verbose_name=_('Staff member'), on_delete=models.CASCADE
    )
    template = models.CharField(
        _('Plugin template'), max_length=250, null=True, blank=True
    )

    def get_short_description(self):
        return self.staffMember.fullName


class StaffMemberListPluginModel(CMSPlugin):
    '''
    The Instructor photo list, instructor bio listing, and instructor directory
    all use this model for configuration.
    '''

    class OrderChoices(models.TextChoices):
        firstName = ('firstName', _('First Name'))
        lastName = ('lastName', _('Last Name'))
        status = ('status', _('Instructor Status'))
        random = ('random', _('Randomly Ordered'))

    statusChoices = MultiSelectField(
        verbose_name=_('Limit to Instructors with Status'),
        choices=Instructor.InstructorStatus.choices,
        default=[
            Instructor.InstructorStatus.roster,
            Instructor.InstructorStatus.assistant,
            Instructor.InstructorStatus.guest
        ],
    )
    orderChoice = models.CharField(_('Order By'), max_length=10, choices=OrderChoices.choices)
    imageThumbnail = models.ForeignKey(
        ThumbnailOption, verbose_name=_('Image thumbnail option'),
        null=True, blank=True, on_delete=models.SET_NULL
    )

    bioRequired = models.BooleanField(_('Exclude staff members with no bio'), default=False)
    photoRequired = models.BooleanField(_('Exclude staff members with no photo'), default=False)
    activeUpcomingOnly = models.BooleanField(
        _('Include only staff members with upcoming classes/events'), default=False
    )

    title = models.CharField(_('Listing Title'), max_length=200, null=True, blank=True)
    template = models.CharField(_('Template'), max_length=250, null=True, blank=True)

    def get_short_description(self):
        desc = self.title or ''
        choices = getattr(self.get_plugin_class(), 'template_choices', [])
        choice_name = [x[1] for x in choices if x[0] == self.template]
        if choice_name:
            if desc:
                desc += ': %s' % choice_name[0]
            else:
                desc = choice_name[0]
        elif self.template:
            if desc:
                desc += ': %s' % self.template
            else:
                desc = self.template
        return desc or self.id


class LocationListPluginModel(CMSPlugin):
    ''' A model for listing of all active locations '''
    template = models.CharField(
        verbose_name=_('Plugin template'), max_length=250, null=True, blank=True
    )

    def get_short_description(self):
        desc = self.id
        choices = getattr(self.get_plugin_class(), 'template_choices', [])
        choice_name = [x[1] for x in choices if x[0] == self.template]
        if choice_name:
            desc = choice_name[0]
        elif self.template:
            desc = self.template
        return desc


class LocationPluginModel(CMSPlugin):
    ''' Individual location directions, etc. use this view '''
    location = models.ForeignKey(
        Location, verbose_name=_('Location'), on_delete=models.CASCADE
    )
    template = models.CharField(_('Plugin template'), max_length=250, null=True, blank=True)

    def get_short_description(self):
        desc = self.location.name or ''
        choices = getattr(self.get_plugin_class(), 'template_choices', [])
        choice_name = [x[1] for x in choices if x[0] == self.template]
        if choice_name:
            if desc:
                desc += ': %s' % choice_name[0]
            else:
                desc = choice_name[0]
        elif self.template:
            if desc:
                desc += ': %s' % self.template
            else:
                desc = self.template
        return desc or self.id


class EventListPluginModel(CMSPlugin):
    '''
    This model is typically used to configure upcoming event listings, but it
    can be customized to a variety of purposes using custom templates, etc.
    '''
    LIMIT_CHOICES = [
        ('S', _('Event start date')),
        ('E', _('Event end date')),
    ]
    EVENT_TYPE_CHOICES = [
        ('S', _('Class Series')),
        ('P', _('Public Events')),
    ]
    SORT_CHOICES = [
        ('A', _('Ascending')),
        ('D', _('Descending')),
    ]

    title = models.CharField(
        _('Custom list title'), max_length=250, default=_('Upcoming Events'), blank=True
    )

    eventType = models.CharField(
        _('Limit to event type'), max_length=1, choices=EVENT_TYPE_CHOICES,
        null=True, blank=True, help_text=_('Leave blank to include all Events.')
    )
    limitNumber = models.PositiveSmallIntegerField(
        _('Limit number'), help_text=_('Leave blank for no restriction'), null=True, blank=True
    )
    sortOrder = models.CharField(
        _('Sort by start time'), max_length=1, choices=SORT_CHOICES, default='A',
        help_text=_('This may be overridden by the particular template in use')
    )

    limitTypeStart = models.CharField(
        _('Limit interval start by'), max_length=1, choices=LIMIT_CHOICES, default='E'
    )
    daysStart = models.SmallIntegerField(
        _('Interval limited to __ days from present'), null=True, blank=True,
        help_text=_(
            '(E.g. enter -30 for an interval that starts with 30 days prior ' +
            'to today) Leave blank for no limit, or enter 0 to limit to future events'
        )
    )
    startDate = models.DateField(
        _('Exact interval start date'), null=True, blank=True,
        help_text=_('Leave blank for no limit (overrides relative interval limits)')
    )

    limitTypeEnd = models.CharField(
        _('Limit interval end by'), max_length=1, choices=LIMIT_CHOICES, default='S'
    )
    daysEnd = models.SmallIntegerField(
        _('Interval limited to __ days from present'), null=True, blank=True,
        help_text=_(
            '(E.g. enter 30 for an interval that ends 30 days from today) Leave ' +
            'blank for no limit, or enter 0 to limit to past events'
        )
    )
    endDate = models.DateField(
        _('Exact interval end date '), null=True, blank=True,
        help_text=_('Leave blank for no limit (overrides relative interval limits)')
    )

    limitToOpenRegistration = models.BooleanField(
        _('Limit to open for registration only'), default=False
    )
    location = models.ManyToManyField(
        Location, verbose_name=_('Limit to locations'),
        help_text=_('Leave blank for no restriction'), blank=True
    )
    weekday = models.PositiveSmallIntegerField(
        _('Limit to weekday'), null=True, blank=True,
        choices=[(x, _(day_name[x])) for x in range(0, 7)]
    )

    eventCategories = models.ManyToManyField(
        PublicEventCategory, verbose_name=_('Limit to public event categories'),
        help_text=_('Leave blank for no restriction'),
        blank=True
    )

    seriesCategories = models.ManyToManyField(
        SeriesCategory, verbose_name=_('Limit to series categories'),
        help_text=_('Leave blank for no restriction'),
        blank=True
    )

    levels = models.ManyToManyField(
        DanceTypeLevel, verbose_name=_('Limit to type and levels'),
        help_text=_('Leave blank for no restriction'),
        blank=True
    )

    cssClasses = models.CharField(
        _('Custom CSS classes'), max_length=250, null=True, blank=True,
        help_text=_('Classes are applied to surrounding &lt;div&gt;')
    )
    template = models.CharField(_('Plugin template'), max_length=250, null=True, blank=True)

    def copy_relations(self, oldinstance):
        self.location.set(oldinstance.location.all())
        self.eventCategories.set(oldinstance.eventCategories.all())
        self.seriesCategories.set(oldinstance.seriesCategories.all())
        self.levels.set(oldinstance.levels.all())

    def get_short_description(self):
        desc = self.title or ''
        choices = getattr(self.get_plugin_class(), 'template_choices', [])
        choice_name = [x[1] for x in choices if x[0] == self.template]
        if choice_name:
            if desc:
                desc += ': %s' % choice_name[0]
            else:
                desc = choice_name[0]
        elif self.template:
            if desc:
                desc += ': %s' % self.template
            else:
                desc = self.template
        return desc or self.id

    class Meta:
        permissions = (
            (
                'choose_custom_plugin_template',
                _('Can enter a custom plugin template for plugins with selectable template.')
            ),
        )
