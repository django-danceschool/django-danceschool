from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _

import unicodecsv as csv


def getExpenseItemsCSV(queryset, scope='instructor'):

    response = HttpResponse(content_type='text/csv')
    if scope == 'instructor':
        response['Content-Disposition'] = 'attachment; filename="paymentHistory.csv"'
    else:
        response['Content-Disposition'] = 'attachment; filename="expenseHistory.csv"'

    writer = csv.writer(response, csv.excel)
    # BOM (optional...Excel needs it to open UTF-8 file properly)
    response.write(u'\ufeff'.encode('utf8'))

    header_list = [
        _('Description'),
        _('Expense Category'),
        _('Hours'),
        _('Wage Rate'),
        _('Total Payment'),
        _('Is Reimbursement'),
        _('Submission Date'),
        _('Event'),
        _('Approved'),
        _('Approval Date'),
        _('Paid'),
        _('Payment Date'),
        _('Payment Method'),
        _('Accrual Date'),
    ]

    if scope != 'instructor':
        header_list += [_('Pay To')]

    writer.writerow(header_list)

    for x in queryset:
        this_row_data = [
            x.description,
            x.category.name,
            x.hours,
            x.wageRate,
            x.total,
            x.reimbursement,
            x.submissionDate,
            x.event,
            x.approved,
            x.approvalDate,
            x.paid,
            x.paymentDate,
            x.paymentMethod,
            x.accrualDate,
        ]

        if scope != 'instructor':
            this_row_data.append(x.payTo)

        writer.writerow(this_row_data)
    return response


def getRevenueItemsCSV(queryset):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="revenueHistory.csv"'

    writer = csv.writer(response, csv.excel)
    # BOM (optional...Excel needs it to open UTF-8 file properly)
    response.write(u'\ufeff'.encode('utf8'))

    header_list = [
        _('Description'),
        _('Revenue Category'),
        _('Gross Total (Pre-Discounts & Vouchers)'),
        _('Net Total'),
        _('Received From'),
        _('Invoice ID'),
        _('Event'),
        _('Submission Date'),
        _('Received'),
        _('Received Date'),
        _('Payment Method'),
        _('Accrual Date'),
    ]
    writer.writerow(header_list)

    for x in queryset:
        this_row_data = [
            x.description,
            x.category.name,
            x.grossTotal,
            x.total,
            getattr(x.receivedFrom, 'name', None),
            getattr(getattr(x.invoiceItem, 'invoice', None), 'id', None),
            x.event,
            x.submissionDate,
            x.received,
            x.receivedDate,
            x.paymentMethod,
            x.accrualDate,
        ]

        writer.writerow(this_row_data)
    return response
