from django.db.models import Q, Value, F, CharField, IntegerField

from danceschool.core.models import Event, EventOccurrence
from .models import GuestList, GuestListName

def getList(
    guestList=None, event=None, events=Event.objects.none(), startTime=None, endTime=None,
    **kwargs
):

    if event:
        events = Event.objects.filter(id=getattr(event, 'id', event))

    if (not events) and startTime and endTime:
        occs = EventOccurrence.objects.filter(
            endTime__gte=startTime, startTime__lte=endTime
        )
        events = Event.objects.filter(eventoccurrence__in=occs).distinct()

    if not events:
        return GuestListName.objects.annotate(
            first=F('firstName'), last=F('lastName'), contact=F('email'),
            modelType=Value(None, output_field=CharField()),
            guestListId=Value(None, output_field=IntegerField()),
            guestType=Value(None, output_field=CharField()),
        ).none()

    applicable_lists = None

    if guestList:
        applicable_lists = GuestList.objects.filter(id__in=getattr(guestList, 'id', guestList))
    else:
        # This is the same logic as the appliesToEvent() method of GuestList
        applicable_lists = GuestList.objects.filter(
            Q(individualEvents__in=events) |
            Q(eventSessions__in=events.filter(session__isnull=False).values_list(
                'session', flat=True
            )) |
            Q(seriesCategories__in=events.filter(
                series__category__isnull=False
            ).values_list('series__category', flat=True)) |
            Q(eventCategories__in=events.filter(
                publicevent__category__isnull=False
            ).values_list('publicevent__category', flat=True))
        )

    queryset = []

    for this_list in applicable_lists:
        if not queryset:
            queryset = this_list.getListForEvents(events, **kwargs).order_by()
        else:
            queryset = queryset.union(
                this_list.getListForEvent(events, **kwargs).order_by()
            )

    return queryset
