from django.http import JsonResponse

from datetime import datetime, timedelta

from danceschool.core.models import Instructor

from .models import InstructorAvailabilitySlot


class EventFeedItem(object):

    def __init__(self,object,**kwargs):
        self.id = 'instructorAvailability_' + str(object.id)
        self.type = 'instructorAvailability'
        self.id_number = object.id
        self.title = object.name
        self.start = object.startTime
        self.end = object.startTime + timedelta(minutes=object.duration)
        self.availableDurations = object.availableDurations
        self.status = object.status
        self.className = ['availabilitySlot','availabilitySlot-%s' % object.status]

        if object.location:
            self.location = object.location.name + '\n' + object.location.address + '\n' + object.location.city + ', ' + object.location.state + ' ' + object.location.zip
            self.location_id = object.location.id
        else:
            self.location = None
            self.location_id = None


# The Jquery fullcalendar app requires a JSON news feed, so this function
# creates the feed from upcoming SeriesClass and Event objects.
def json_availability_feed(request,instructor_id=None):
    if not instructor_id:
        return JsonResponse({})

    startDate = request.GET.get('start','')
    endDate = request.GET.get('end','')

    time_filter_dict_events = {}
    if startDate:
        time_filter_dict_events['startTime__gte'] = datetime.strptime(startDate,'%Y-%m-%d')
    if endDate:
        time_filter_dict_events['startTime__lte'] = datetime.strptime(endDate,'%Y-%m-%d') + timedelta(days=1)

    this_instructor = Instructor.objects.get(id=instructor_id)

    availability = InstructorAvailabilitySlot.objects.filter(
        instructor=this_instructor,
    ).filter(**time_filter_dict_events)

    if hasattr(request.user,'staffmember') and request.user.staffmember == this_instructor:
        eventlist = [EventFeedItem(x).__dict__ for x in availability]
    else:
        eventlist = [EventFeedItem(x).__dict__ for x in availability if x.isAvailable]

    return JsonResponse(eventlist,safe=False)
