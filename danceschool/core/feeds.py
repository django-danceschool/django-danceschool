from django.http import JsonResponse
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from django.conf import settings

from django_ical.views import ICalFeed
from datetime import datetime, timedelta

from .models import EventOccurrence, StaffMember, Event
from .constants import getConstant


# Because our calendar will have both series classes and non-recurring events
# in it, we need to create a custom class with properties assigned appropriately
# to iterate through in the feed generation process
class EventFeedItem(object):

    def __init__(self,object,**kwargs):
        self.id = 'event_' + str(object.event.id) + '_' + str(object.id)
        self.type = 'event'
        self.id_number = object.event.id
        self.title = object.event.name
        self.description = object.event.description
        self.start = object.startTime
        self.end = object.endTime
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
    timezone = settings.TIME_ZONE

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
            return [EventFeedItem(x) for x in item_set]
        else:
            return [EventFeedItem(x) for x in item_set.filter(event__eventstaffmember__staffmember__feedKey=obj)]

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
def json_event_feed(request,instructorFeedKey=''):

    if not getConstant('calendar__calendarFeedEnabled'):
        return JsonResponse({})

    startDate = request.GET.get('start','')
    endDate = request.GET.get('end','')

    time_filter_dict_series = {}
    time_filter_dict_events = {}
    if startDate:
        time_filter_dict_series['startTime__gte'] = datetime.strptime(startDate,'%Y-%m-%d')
        time_filter_dict_events['startTime__gte'] = datetime.strptime(startDate,'%Y-%m-%d')
    if endDate:
        time_filter_dict_series['endTime__lte'] = datetime.strptime(endDate,'%Y-%m-%d') + timedelta(days=1)
        time_filter_dict_events['endTime__lte'] = datetime.strptime(endDate,'%Y-%m-%d') + timedelta(days=1)

    item_set = EventOccurrence.objects.exclude(event__status=Event.RegStatus.hidden).filter(**time_filter_dict_events).filter(Q(event__series__isnull=False) | Q(event__publicevent__isnull=False)).order_by('-startTime')

    if not instructorFeedKey:
        eventlist = [EventFeedItem(x).__dict__ for x in item_set]
    else:
        eventlist = [EventFeedItem(x).__dict__ for x in item_set.filter(event__eventstaffmember__staffMember__feedKey=instructorFeedKey)]

    return JsonResponse(eventlist,safe=False)
