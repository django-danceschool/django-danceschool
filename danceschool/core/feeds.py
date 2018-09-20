from django.http import JsonResponse
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from django.utils import timezone

from django_ical.views import ICalFeed
from datetime import datetime, timedelta
import pytz

from .models import EventOccurrence, StaffMember, Event
from .constants import getConstant
from .utils.timezone import ensure_timezone


# Because our calendar will have both series classes and non-recurring events
# in it, we need to create a custom class with properties assigned appropriately
# to iterate through in the feed generation process
class EventFeedItem(object):

    def __init__(self,object,**kwargs):

        timeZone = pytz.timezone(getattr(settings,'TIME_ZONE','UTC'))
        if kwargs.get('timeZone',None):
            try:
                timeZone = pytz.timezone(kwargs.get('timeZone',None))
            except pytz.exceptions.UnknownTimeZoneError:
                pass

        self.id = 'event_' + str(object.event.id) + '_' + str(object.id)
        self.type = 'event'
        self.id_number = object.event.id
        self.title = object.event.name
        self.description = object.event.shortDescription
        self.start = timezone.localtime(object.startTime,timeZone) \
            if timezone.is_aware(object.startTime) else object.startTime
        self.end = timezone.localtime(object.endTime,timeZone) \
            if timezone.is_aware(object.endTime) else object.endTime
        self.color = object.event.displayColor
        self.url = object.event.get_absolute_url()
        if hasattr(object,'event.location'):
            self.location = object.event.location.name + '\n' + object.event.location.address + '\n' + object.event.location.city + ', ' + object.event.location.state + ' ' + object.event.location.zip
        else:
            self.location = None


class EventFeed(ICalFeed):
    """
    A simple event calender
    """
    timezone = getattr(settings,'TIME_ZONE','UTC')

    def get_object(self,request,instructorFeedKey=''):
        if instructorFeedKey:
            return instructorFeedKey
        else:
            return None

    def title(self,obj):
        businessName = getConstant('contact__businessName')

        if not obj:
            return _('%s Events Calendar' % businessName)
        else:
            this_instructor = StaffMember.objects.filter(**{'feedKey': obj}).values('firstName','lastName').first()
            return _('%s Instructor Calendar for %s %s' % (businessName,this_instructor['firstName'],this_instructor['lastName']))

    def description(self):
        return _('Calendar for %s' % getConstant('contact__businessName'))

    def items(self,obj):
        if not getConstant('calendar__calendarFeedEnabled'):
            return []

        item_set = EventOccurrence.objects.exclude(event__status=Event.RegStatus.hidden).filter(Q(event__series__isnull=False) | Q(event__publicevent__isnull=False)).order_by('-startTime')

        if not obj:
            # Public calendar does not show hidden Events _or_ link-only registration Events
            return [EventFeedItem(x) for x in item_set.exclude(event__status=Event.RegStatus.linkOnly)[:100]]
        else:
            # Private calendars do show link-only registration Events
            return [EventFeedItem(x) for x in item_set.filter(event__eventstaffmember__staffMember__feedKey=obj)[:100]]

    def item_guid(self,item):
        return item.id + '@' + item.url

    def item_title(self, item):
        return item.title

    def item_link(self, item):
        return item.url

    def item_location(self, item):
        return item.location

    def item_description(self, item):
        return item.description

    def item_start_datetime(self, item):
        return item.start

    def item_end_datetime(self, item):
        return item.end


# The Jquery fullcalendar app requires a JSON news feed, so this function
# creates the feed from upcoming SeriesClass and Event objects.
def json_event_feed(request,instructorFeedKey='',locationId=None,roomId=None):

    if not getConstant('calendar__calendarFeedEnabled'):
        return JsonResponse({})

    startDate = request.GET.get('start','')
    endDate = request.GET.get('end','')
    timeZone = request.GET.get('timezone',getattr(settings,'TIME_ZONE','UTC'))

    filters = Q(event__month__isnull=False) & Q(event__year__isnull=False) & (Q(event__series__isnull=False) | Q(event__publicevent__isnull=False))
    exclusions = Q(event__status=Event.RegStatus.hidden)
    if startDate:
        limit_time = ensure_timezone(datetime.strptime(startDate,'%Y-%m-%d'))
        filters = filters & Q(startTime__gte=limit_time)
    if endDate:
        limit_time = ensure_timezone(datetime.strptime(endDate,'%Y-%m-%d'))
        filters = filters & Q(endTime__lte=limit_time + timedelta(days=1))

    if locationId:
        filters = filters & Q(event__location__id=locationId)
    if roomId:
        filters = filters & Q(event__room_id=roomId)

    if instructorFeedKey:
        # Private calendars do show link-only registration Events
        filters = filters & Q(event__eventstaffmember__staffMember__feedKey=instructorFeedKey)
    else:
        # Public calendar does not show hidden Events _or_ link-only registration Events
        exclusions = exclusions | Q(event__status=Event.RegStatus.linkOnly)

    item_set = EventOccurrence.objects.exclude(exclusions).filter(filters).order_by('-startTime')
    eventlist = [EventFeedItem(x,timeZone=timeZone).__dict__ for x in item_set]
    return JsonResponse(eventlist,safe=False)
