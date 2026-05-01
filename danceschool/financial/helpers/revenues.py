from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dateutil.relativedelta import relativedelta

from danceschool.core.constants import getConstant
from danceschool.core.models import InvoiceItem

from ..models import RevenueItem


def createRevenueItemsForRegistrations(request=None, datetimeTuple=None):

    if hasattr(request, 'user'):
        submissionUser = request.user
    else:
        submissionUser = None

    this_category = getConstant('financial__registrationsRevenueCat')

    filters_events = {
        'revenueitem__isnull': True,
        'eventRegistration__isnull': False,
        'eventRegistration__registration__final': True,
    }

    if datetimeTuple:
        timelist = list(datetimeTuple)
        timelist.sort()

        filters_events[
            'eventRegistration__event__eventoccurrence__startTime__gte'
        ] = timelist[0]
        filters_events[
            'eventRegistration__event__eventoccurrence__startTime__lte'
        ] = timelist[1]
    else:
        c = getConstant('financial__autoGenerateRevenueRegistrationsWindow') or 0
        if c > 0:
            filters_events[
                'eventRegistration__event__eventoccurrence__startTime__gte'
            ] = timezone.now() - relativedelta(months=c)

    for item in InvoiceItem.objects.filter(**filters_events).distinct():
        if item.invoice.registration.paidOnline:
            received = True
        else:
            received = False

        revenue_description = _('Event Registration ') + \
            str(item.eventRegistration.id) + ': ' + \
            item.invoice.registration.fullName
        RevenueItem.objects.create(
            invoiceItem=item,
            category=this_category,
            description=revenue_description,
            submissionUser=submissionUser,
            grossTotal=item.grossTotal,
            total=item.total,
            received=received,
            receivedDate=item.invoice.modifiedDate
        )
