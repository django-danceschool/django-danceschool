from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from cms.models.pluginmodel import CMSPlugin

from datetime import datetime, timedelta

from .models import InstructorListPluginModel, LocationPluginModel, LocationListPluginModel, EventListPluginModel, Instructor, Event, Series, PublicEvent, Location
from .mixins import PluginTemplateMixin
from .registries import plugin_templates_registry, PluginTemplateBase


class InstructorListPlugin(PluginTemplateMixin, CMSPluginBase):
    model = InstructorListPluginModel
    name = _('Set of Instructor Images or Bios')
    render_template = 'core/instructor_image_set.html'
    cache = True
    module = _('Staff')

    def render(self, context, instance, placeholder):
        context = super(InstructorListPlugin,self).render(context,instance,placeholder)

        listing = Instructor.objects.all()

        if instance.statusChoices:
            listing = listing.filter(status__in=instance.statusChoices)
        else:
            listing = listing.exclude(status__in=[
                Instructor.InstructorStatus.hidden,
                Instructor.InstructorStatus.retired,
                Instructor.InstructorStatus.retiredGuest
            ])

        if instance.photoRequired:
            listing = listing.filter(image__isnull=False)
        if instance.bioRequired:
            listing = listing.filter(bio__isnull=False).exclude(bio__exact='')

        if instance.activeUpcomingOnly:
            listing = listing.filter(eventstaffmember__event__endTime__gte=timezone.now()).distinct()

        if instance.orderChoice == 'firstName':
            listing = listing.order_by('firstName','lastName')
        elif instance.orderChoice == 'status':
            listing = listing.order_by('status','lastName','firstName')
        elif instance.orderChoice == 'random':
            listing = listing.order_by('?')
        else:
            listing = listing.order_by('lastName','firstName')

        context.update({
            'list_title': instance.title,
            'instructor_list': listing,
            'thumbnail': instance.imageThumbnail,
        })

        if instance.imageThumbnail:
            context['thumbnail_dimensions'] = '%sx%s' % (instance.imageThumbnail.width, instance.imageThumbnail.height)
        return context


class LocationListPlugin(PluginTemplateMixin, CMSPluginBase):
    model = LocationListPluginModel
    name = _('Information on All Public Locations')
    render_template = 'core/location_directions.html'
    module = _('Locations')

    def render(self, context, instance, placeholder):
        ''' Allows this plugin to use templates designed for a list of locations. '''
        context = super(LocationListPlugin,self).render(context,instance,placeholder)
        context['location_list'] = Location.objects.filter(status=Location.StatusChoices.active)
        return context


class LocationPlugin(PluginTemplateMixin, CMSPluginBase):
    model = LocationPluginModel
    name = _('Individual Location Information')
    render_template = 'core/location_directions.html'
    cache = True
    module = _('Locations')

    def render(self, context, instance, placeholder):
        ''' Allows this plugin to use templates designed for a list of locations. '''
        context = super(LocationPlugin,self).render(context,instance,placeholder)
        context['location_list'] = [instance.location,]
        return context


class EventListPlugin(PluginTemplateMixin, CMSPluginBase):
    model = EventListPluginModel
    name = _('List of Events')
    cache = True
    module = _('Events')
    render_template = 'core/events_grouped_list.html'

    fieldsets = (
        (None, {
            'fields': ('title','eventType','template','cssClasses')
        }),
        (_('Limit Start Date'), {
            'fields': ('limitTypeStart','daysStart','startDate'),
        }),
        (_('Limit End Date'), {
            'fields': ('limitTypeEnd','daysEnd','endDate'),
        }),
        (_('Limit Number'), {
            'classes': ('collapse',),
            'fields': ('limitNumber','sortOrder'),
        }),
        (_('Limit Categories/Levels'), {
            'classes': ('collapse',),
            'fields': ('eventCategories','seriesCategories','levels'),
        }),
        (_('Other Restrictions'), {
            'classes': ('collapse',),
            'fields': ('limitToOpenRegistration','location','weekday'),
        })
    )

    def render(self, context, instance, placeholder):
        context = super(EventListPlugin,self).render(context,instance,placeholder)

        listing = Event.objects.exclude(status__in=[Event.RegStatus.hidden, Event.RegStatus.linkOnly])

        if instance.eventType == 'S':
            listing = listing.instance_of(Series)
        elif instance.eventType == 'P':
            listing = listing.instance_of(PublicEvent)

        filters = {}

        startKey = 'endTime__gte'
        endKey = 'startTime__lte'

        if instance.limitTypeStart == 'S':
            startKey = 'startTime__gte'
        if instance.limitTypeEnd == 'E':
            endKey = 'endTime__lte'

        if instance.startDate:
            filters[startKey] = datetime.combine(instance.startDate,datetime.min.time())
        elif instance.daysStart is not None:
            filters[startKey] = timezone.now() + timedelta(days=instance.daysStart)

        if instance.endDate:
            filters[endKey] = datetime.combine(instance.endDate,datetime.max.time())
        elif instance.daysEnd is not None:
            filters[endKey] = timezone.now() + timedelta(days=instance.daysEnd)

        if instance.limitToOpenRegistration:
            filters['registrationOpen'] = True

        if instance.location.all():
            filters['location__in'] = instance.location.all()

        if instance.eventCategories.all():
            filters['publicevent__category__in'] = instance.eventCategories.all()

        if instance.seriesCategories.all():
            filters['series__category__in'] = instance.seriesCategories.all()

        if instance.levels.all():
            filters['series__classDescription__danceTypeLevel__in'] = instance.levels.all()

        # Python calendar module indexes weekday differently from Django
        if instance.weekday is not None:
            filters['startTime__week_day'] = (instance.weekday + 2) % 7

        order_by = '-startTime' if instance.sortOrder == 'D' else 'startTime'
        listing = listing.filter(**filters).order_by(order_by)[:instance.limitNumber]

        context.update({
            'event_list': listing,
        })
        return context


class PublicCalendarPlugin(CMSPluginBase):
    model = CMSPlugin
    name = _('Public Calendar')
    render_template = 'core/public_calendar.html'
    cache = True
    module = _('Events')


plugin_pool.register_plugin(InstructorListPlugin)
plugin_pool.register_plugin(LocationPlugin)
plugin_pool.register_plugin(LocationListPlugin)
plugin_pool.register_plugin(EventListPlugin)
plugin_pool.register_plugin(PublicCalendarPlugin)


@plugin_templates_registry.register
class InstructorImageSetTemplate(PluginTemplateBase):
    plugin = 'InstructorListPlugin'
    template_name = 'core/instructor_image_set.html'
    description = _('Instructor Images')


@plugin_templates_registry.register
class InstructorListTemplate(PluginTemplateBase):
    plugin = 'InstructorListPlugin'
    template_name = 'core/instructor_list.html'
    description = _('Instructor Bios with Images')


@plugin_templates_registry.register
class LocationDirectionsTemplate(PluginTemplateBase):
    plugin = 'LocationListPlugin'
    template_name = 'core/location_directions.html'
    description = _('Directions for Each Location')


@plugin_templates_registry.register
class SingleLocationDirectionsTemplate(PluginTemplateBase):
    plugin = 'LocationPlugin'
    template_name = 'core/location_directions.html'
    description = _('Directions for This Location')


@plugin_templates_registry.register
class EventListPluginTemplate(PluginTemplateBase):
    plugin = 'EventListPlugin'
    template_name = 'core/events_grouped_list.html'
    description = _('Default Grouped List of Events')
