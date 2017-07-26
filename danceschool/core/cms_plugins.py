from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from cms.models.pluginmodel import CMSPlugin

from datetime import datetime, timedelta

from .models import InstructorListPluginModel, LocationPluginModel, LocationListPluginModel, EventListPluginModel, Instructor, Event, Series, PublicEvent, Location
from .mixins import PluginTemplateMixin


class InstructorListPlugin(PluginTemplateMixin, CMSPluginBase):
    model = InstructorListPluginModel
    name = _('Set of Instructor Images or Bios')
    render_template = 'core/instructor_image_set.html'
    template_choices = [
        ('core/instructor_image_set.html',_('Instructor Images')),
        ('core/instructor_list.html', _('Instructor Bios with Images')),
    ]
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
    template_choices = [('core/location_directions.html',_('Directions for Each Location'))]
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
    template_choices = [('core/location_directions.html',_('Directions for Each Location'))]
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

    render_template = 'core/events_bymonth_list.html'
    template_choices = [
        ('core/events_bymonth_list.html',_('Default List of Events By Month')),
    ]

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
        (_('Other Restrictions'), {
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

        if instance.location:
            filters['location'] = instance.location

        # Python calendar module indexes weekday differently from Django
        if instance.weekday is not None:
            filters['startTime__week_day'] = (instance.weekday + 2) % 7

        listing = listing.filter(**filters)

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
