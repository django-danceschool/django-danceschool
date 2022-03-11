from django.db.models import Q

from danceschool.core.models import Event, EventOccurrence, Customer
from .models import GuestList

def getList(
    guestList=None, event=None, events=[], startTime=None, endTime=None,
    **kwargs
):

    # Do not pass a specific event if passing events as a queryset because then append will fail.
    if event:
        events.append(event)

    if (not events) and startTime and endTime:
        occs = EventOccurrence.objects.filter(
            endTime__gte=startTime, startTime__lte=endTime
        )
        events = Event.objects.filter(eventoccurrence__in=occs).distinct()

    if not events:
        return Customer.objects.none()

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

    queryset = Customer.objects.none().order_by()

    for this_list in applicable_lists:
        for this_event in events:
            queryset = queryset.union(
                this_list.getListForEvent(this_event, **kwargs).order_by()
            )

    # Now that all the subqueries are together, order by the common
    # lastName and firstName fields.
    queryset = queryset.values(
        'id', 'modelType', 'guestListId', 'firstName', 'lastName',
        'guestType',
    ).distinct().order_by(
        'lastName', 'firstName'
    )

    return queryset
