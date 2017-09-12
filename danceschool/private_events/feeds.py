from django_ical.views import ICalFeed
from django.http import JsonResponse
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User

import pytz
from datetime import datetime, timedelta

from danceschool.core.models import StaffMember
from danceschool.core.constants import getConstant
from danceschool.core.utils.timezone import ensure_timezone

from .models import EventOccurrence


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

        self.id = 'privateEvent_' + str(object.event.id)
        self.type = 'privateEvent'
        self.id_number = object.event.id
        self.title = object.event.name
        self.description = object.event.description

        if hasattr(object.event,'category') and object.event.category:
            self.category = object.event.category.name
            self.color = object.event.category.displayColor
        else:
            self.category = None
            self.color = getConstant('calendar__defaultEventColor')
        self.start = timezone.localtime(object.startTime,timeZone)
        self.end = timezone.localtime(object.endTime,timeZone)
        self.allDay = object.allDayForDate(object.startTime)
        if hasattr(object,'event.location'):
            self.location = object.event.location.name + '\n' + object.event.location.address + '\n' + object.event.location.city + ', ' + object.event.location.state + ' ' + object.event.location.zip
            self.room = getattr(object.event,'room',None)
        else:
            self.location = None
            self.room = None
        self.url = object.event.link


class EventFeed(ICalFeed):
    """
    A simple event calender
    """
    timezone = getattr(settings,'TIME_ZONE','UTC')
    description = _('Calendar for %s' % getConstant('contact__businessName'))

    def get_member(self,obj):
        member = None
        try:
            member = StaffMember.objects.get(userAccount=obj)
        except ObjectDoesNotExist:
            pass
        return member

    def get_object(self,request,instructorFeedKey=''):
        if instructorFeedKey:
            try:
                return User.objects.get(staffmember__feedKey=instructorFeedKey)
            except (ValueError, ObjectDoesNotExist):
                pass
        return request.user

    def title(self,obj):
        this_instructor = self.get_member(obj)
        if not this_instructor:
            return _('%s Events Calendar' % getConstant('contact__businessName'))
        return _('%s Staff Calendar for %s' % (getConstant('contact__businessName'), this_instructor.fullName))

    def items(self,obj):
        if not getattr(obj,'is_staff') or not getConstant('calendar__privateCalendarFeedEnabled'):
            return []

        this_user = obj
        instructor_groups = list(this_user.groups.all().values_list('id',flat=True))

        occurrences = EventOccurrence.objects.filter(event__privateevent__isnull=False).filter(
            Q(event__privateevent__displayToGroup__in=instructor_groups) |
            Q(event__privateevent__displayToUsers=this_user) |
            (Q(event__privateevent__displayToGroup__isnull=True) & Q(event__privateevent__displayToUsers__isnull=True))).order_by('-startTime')

        return [EventFeedItem(x) for x in occurrences]

    def item_guid(self, item):
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


def json_event_feed(request,location_id=None,room_id=None):
    '''
    The Jquery fullcalendar app requires a JSON news feed, so this function
    creates the feed from upcoming PrivateEvent objects
    '''

    if not getConstant('calendar__privateCalendarFeedEnabled') or not request.user.is_staff:
        return JsonResponse({})
    this_user = request.user

    startDate = request.GET.get('start','')
    endDate = request.GET.get('end','')
    timeZone = request.GET.get('timezone',getattr(settings,'TIME_ZONE','UTC'))

    time_filter_dict_events = {}
    if startDate:
        time_filter_dict_events['startTime__gte'] = ensure_timezone(datetime.strptime(startDate,'%Y-%m-%d'))
    if endDate:
        time_filter_dict_events['endTime__lte'] = ensure_timezone(datetime.strptime(endDate,'%Y-%m-%d')) + timedelta(days=1)

    instructor_groups = list(this_user.groups.all().values_list('id',flat=True))

    filters = Q(event__privateevent__isnull=False) & (
        Q(event__privateevent__displayToGroup__in=instructor_groups) |
        Q(event__privateevent__displayToUsers=this_user) |
        (Q(event__privateevent__displayToGroup__isnull=True) & Q(event__privateevent__displayToUsers__isnull=True))
    )

    if location_id:
        filters = filters & Q(event__location__id=location_id)
    if room_id:
        filters = filters & Q(event__room_id=room_id)

    occurrences = EventOccurrence.objects.filter(filters).filter(**time_filter_dict_events).order_by('-startTime')

    eventlist = [EventFeedItem(x,timeZone=timeZone).__dict__ for x in occurrences]

    return JsonResponse(eventlist,safe=False)
