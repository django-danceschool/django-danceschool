from django.http import JsonResponse
from danceschool.core.models import InvoiceItem


def updateEventRegistrations(request):
    '''
    This function handles the filtering of available eventregistration-related
    invoice items and is used on the revenue reporting form.
    '''
    if not (request.method == 'POST' and request.POST.get('event')):
        return JsonResponse({})

    invoiceItems = InvoiceItem.objects.filter(**{'finalEventRegistration__event__id': request.POST.get('event')})

    outRegs = {}
    for option in invoiceItems:
        outRegs[str(option.id)] = option.__str__()

    return JsonResponse({
        'id_invoiceItem': outRegs,
    })
