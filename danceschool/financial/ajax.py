from django.http import JsonResponse
from danceschool.core.models import EventRegistration


def updateEventRegistrations(request):
    '''
    This function handles the filtering of available eventregistrations and is
    used on the revenue reporting form.
    '''
    if not (request.method == 'POST' and request.POST.get('event')):
        return JsonResponse({})

    eventRegistrations = EventRegistration.objects.filter(**{'event__id': request.POST.get('event')})

    outRegs = {}
    for option in eventRegistrations:
        outRegs[str(option.id)] = option.__str__()

    return JsonResponse({
        'id_eventregistration': outRegs,
    })
