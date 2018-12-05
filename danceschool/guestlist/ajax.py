from django.http import JsonResponse

from danceschool.core.models import Event

from .models import GuestList


def getGuestList(request):
    '''
    This function handles the filtering of available eventregistration-related
    invoice items and is used on the revenue reporting form.
    '''
    if not (
        request.method == 'POST' and
        request.POST.get('guestlist_id') and
        request.POST.get('event_id') and
        request.user.is_authenticated and
        request.user.has_perm('guestlist.view_guestlist')
    ):
        return JsonResponse({})

    guestList = GuestList.objects.filter(id=request.POST.get('guestlist_id')).first()
    event = Event.objects.filter(id=request.POST.get('event_id')).first()

    if not guestList or not event:
        return JsonResponse({})

    return JsonResponse({
        'names': guestList.getListForEvent(event),
    })
