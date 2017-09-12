from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
from django.http import Http404
from django.db.models import Q

from datetime import datetime, timedelta
import pytz

from danceschool.core.models import Instructor
from danceschool.core.utils.timezone import ensure_timezone

from .models import InstructorAvailabilitySlot, PrivateLessonEvent


class AvailabilityFeedItem(object):

    def __init__(self,object,**kwargs):

        timeZone = pytz.timezone(getattr(settings,'TIME_ZONE','UTC'))
        if kwargs.get('timeZone',None):
            try:
                timeZone = pytz.timezone(kwargs.get('timeZone',None))
            except pytz.exceptions.UnknownTimeZoneError:
                pass

        self.id = 'instructorAvailability_' + str(object.id)
        self.type = 'instructorAvailability'
        self.id_number = object.id
        self.title = object.name
        self.start = timezone.localtime(object.startTime,timeZone) \
            if timezone.is_aware(object.startTime) else object.startTime
        self.end = self.start + timedelta(minutes=object.duration)
        self.availableDurations = object.availableDurations
        self.availableRoles = object.availableRoles
        self.pricingTier = getattr(object.pricingTier,'name',None)
        self.pricingTier_id = getattr(object.pricingTier,'id',None)
        self.onlinePrice = getattr(object.pricingTier,'onlinePrice',None)
        self.doorPrice = getattr(object.pricingTier,'doorPrice',None)
        self.status = object.status
        self.className = ['availabilitySlot','availabilitySlot-%s' % object.status]

        if object.location:
            self.location = object.location.name + '\n' + object.location.address + '\n' + object.location.city + ', ' + object.location.state + ' ' + object.location.zip
            self.location_id = object.location.id
        else:
            self.location = None
            self.location_id = None

        if object.room:
            self.room_id = object.room.id
        else:
            self.room_id = None


class PrivateLessonFeedItem(object):

    def __init__(self,object,**kwargs):

        timeZone = pytz.timezone(getattr(settings,'TIME_ZONE','UTC'))
        if kwargs.get('timeZone',None):
            try:
                timeZone = pytz.timezone(kwargs.get('timeZone',None))
            except pytz.exceptions.UnknownTimeZoneError:
                pass

        self.id = 'privateLesson_' + str(object.id)
        self.type = 'privateLesson'
        self.id_number = object.id
        self.title = object.nameAndDate(withDate=False)
        self.start = timezone.localtime(object.startTime,timeZone) \
            if timezone.is_aware(object.startTime) else object.startTime
        self.end = timezone.localtime(object.endTime,timeZone) \
            if timezone.is_aware(object.endTime) else object.endTime
        if getattr(object,'location',None):
            self.location = object.location.name + '\n' + object.location.address + '\n' + object.location.city + ', ' + object.location.state + ' ' + object.location.zip
            self.room = getattr(object.room,'name',None)
        else:
            self.location = None
            self.room = None


# This function creates a JSON feed of all available private lesson
# slots so that lessons may be booked using JQuery fullcalendar.
def json_availability_feed(request,instructor_id=None):
    if not instructor_id:
        return JsonResponse({})

    startDate = request.GET.get('start','')
    endDate = request.GET.get('end','')
    timeZone = request.GET.get('timezone',getattr(settings,'TIME_ZONE','UTC'))
    hideUnavailable = request.GET.get('hideUnavailable', False)

    time_filter_dict_events = {}
    if startDate:
        time_filter_dict_events['startTime__gte'] = ensure_timezone(datetime.strptime(startDate,'%Y-%m-%d'))
    if endDate:
        time_filter_dict_events['startTime__lte'] = ensure_timezone(datetime.strptime(endDate,'%Y-%m-%d')) + timedelta(days=1)

    this_instructor = Instructor.objects.get(id=instructor_id)

    availability = InstructorAvailabilitySlot.objects.filter(
        instructor=this_instructor,
    ).filter(**time_filter_dict_events)

    if (
        ((
            hasattr(request.user,'staffmember') and request.user.staffmember == this_instructor and
            request.user.has_perm('private_lessons.edit_own_availability')
        ) or
            request.user.has_perm('private_lessons.edit_others_availability')
        ) and not hideUnavailable
    ):
        eventlist = [AvailabilityFeedItem(x,timeZone=timeZone).__dict__ for x in availability]
    else:
        eventlist = [AvailabilityFeedItem(x,timeZone=timeZone).__dict__ for x in availability if x.isAvailable]

    return JsonResponse(eventlist,safe=False)


def json_lesson_feed(request,location_id=None,room_id=None,show_others=False):
    '''
    This function displays a JSON feed of all lessons scheduled, optionally
    filtered by location. If show_others is specified, it requires that the
    user has permission to see all other instructor's lessons as well.
    '''
    if not request.user or not request.user.is_staff:
        raise Http404()

    # Don't allow individuals to see others' lessons without permission
    if not request.user.has_perm('private_lessons.view_others_lessons'):
        show_others = False

    this_instructor = getattr(request.user,'staffmember',None)
    startDate = request.GET.get('start','')
    endDate = request.GET.get('end','')
    timeZone = request.GET.get('timezone',getattr(settings,'TIME_ZONE','UTC'))

    filters = Q(instructoravailabilityslot__status=InstructorAvailabilitySlot.SlotStatus.booked)
    if not show_others:
        filters = filters & Q(eventstaffmember__staffMember=this_instructor)

    if startDate:
        filters = filters & Q(startTime__gte=ensure_timezone(datetime.strptime(startDate,'%Y-%m-%d')))
    if endDate:
        filters = filters & Q(endTime__lte=ensure_timezone(datetime.strptime(endDate,'%Y-%m-%d')) + timedelta(days=1))

    if location_id:
        filters = filters & Q(location__id=location_id)
    if room_id:
        filters = filters & Q(room_id=room_id)

    lessons = PrivateLessonEvent.objects.filter(filters).distinct()

    eventlist = [PrivateLessonFeedItem(x,timeZone=timeZone).__dict__ for x in lessons]
    return JsonResponse(eventlist,safe=False)
