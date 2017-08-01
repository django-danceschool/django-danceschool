from django.db.models import Sum, Count
from django.db.models.functions import ExtractYear, ExtractMonth
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from datetime import datetime
from dateutil.relativedelta import relativedelta
import unicodecsv as csv
from calendar import month_name

from danceschool.core.constants import getConstant
from danceschool.core.models import Registration, Event, EventStaffMember, InvoiceItem
from danceschool.core.utils.timezone import ensure_timezone

from .constants import EXPENSE_BASES
from .models import ExpenseItem, ExpenseCategory, RevenueItem, RevenueCategory


def getExpenseItemsCSV(queryset, scope='instructor'):

    response = HttpResponse(content_type='text/csv')
    if scope == 'instructor':
        response['Content-Disposition'] = 'attachment; filename="paymentHistory.csv"'
    else:
        response['Content-Disposition'] = 'attachment; filename="expenseHistory.csv"'

    writer = csv.writer(response, csv.excel)
    response.write(u'\ufeff'.encode('utf8'))  # BOM (optional...Excel needs it to open UTF-8 file properly)

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
        _('Paid'),
        _('Payment Date')
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
            x.paid,
            x.paymentDate
        ]

        if scope != 'instructor':
            if x.payToUser:
                this_row_data.append(x.payToUser.first_name + ' ' + x.payToUser.last_name)
            elif x.payToLocation:
                this_row_data.append(_('Location: ') + x.payToLocation.name)
            elif x.payToName:
                this_row_data.append(x.payToName)
            else:
                this_row_data.append('')

        writer.writerow(this_row_data)
    return response


def getRevenueItemsCSV(queryset):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="revenueHistory.csv"'

    writer = csv.writer(response, csv.excel)
    response.write(u'\ufeff'.encode('utf8'))  # BOM (optional...Excel needs it to open UTF-8 file properly)

    header_list = [
        _('Description'),
        _('Revenue Category'),
        _('Gross Total (Pre-Discounts & Vouchers)'),
        _('Net Total'),
        _('Received From'),
        _('Registration'),
        _('Event'),
        _('Received'),
        _('Received Date')
    ]
    writer.writerow(header_list)

    for x in queryset:
        this_row_data = [
            x.description,
            x.category.name,
            x.grossTotal,
            x.total
        ]
        if x.registration:
            this_row_data.append(x.registration.fullName)
        else:
            this_row_data.append(x.receivedFromName)
        this_row_data += [
            x.registration,
            x.event,
            x.received,
            x.receivedDate
        ]

        writer.writerow(this_row_data)
    return response


# Create associated tasks for items
def createExpenseItemsForVenueRental(request=None,datetimeTuple=None):

    filters = {'venueexpense': None,'location__rentalRate__gt': 0}

    if datetimeTuple:
        timelist = list(datetimeTuple)
        timelist.sort()

        filters['eventoccurrence__startTime__gte'] = timelist[0]
        filters['eventoccurrence__startTime__lte'] = timelist[1]
    else:
        c = getConstant('financial__autoGenerateExpensesVenueRentalWindow') or 0
        if c > 0:
            filters['eventoccurrence__startTime__gte'] = timezone.now() - relativedelta(months=c)

    # Only create expense items for venues with a positive rental rate
    for event in Event.objects.filter(**filters).distinct():
        replacements = {
            'month': month_name[event.month],
            'year': event.year,
            'type': _('Event/Series venue rental'),
            'location': event.location.name,
            'for': _('for'),
            'name': event.name,
        }
        expense_description = '%(month)s %(year)s %(type)s: %(location)s %(for)s %(name)s' % replacements

        if hasattr(request,'user'):
            submissionUser = request.user
        else:
            submissionUser = None

        hoursRented = event.duration
        rentalRate = event.location.rentalRate
        total = hoursRented * rentalRate

        this_category = getConstant('financial__venueRentalExpenseCat')

        ExpenseItem.objects.create(eventvenue=event,category=this_category,description=expense_description,submissionUser=submissionUser,hours=hoursRented,wageRate=rentalRate,total=total)


def createExpenseItemsForCompletedEvents(request=None,datetimeTuple=None):

    filters = {'expenseitem': None}

    if datetimeTuple:
        timelist = list(datetimeTuple)
        timelist.sort()

        filters['event__eventoccurrence__startTime__gte'] = timelist[0]
        filters['event__eventoccurrence__startTime__lte'] = timelist[1]
    else:
        c = getConstant('financial__autoGenerateExpensesCompletedEventsWindow') or 0
        if c > 0:
            filters['event__eventoccurrence__startTime__gte'] = timezone.now() - relativedelta(months=c)

    for member in EventStaffMember.objects.filter(**filters).distinct():
        # If an EventStaffMember object for a completed class has no associated ExpenseItem, then create one.
        if member.event.isCompleted and not hasattr(member,'expenseitem'):
            replacements = {
                'month': month_name[member.event.month],
                'year': member.event.year,
                'type': _('event'),
                'name': member.event.name,
                'memberName': member.staffMember.fullName,
            }
            expense_description = '%(month)s %(year)s %(type)s: %(name)s - %(memberName)s' % replacements

            if hasattr(request,'user'):
                submissionUser = request.user
            else:
                submissionUser = None

            # Hours should be net of substitutes
            hours_taught = member.netHours
            wage_rate = member.category.defaultRate

            if member.category == getConstant('general__eventStaffCategoryAssistant'):
                this_category = getConstant('financial__assistantClassInstructionExpenseCat')
            elif member.category in [getConstant('general__eventStaffCategoryInstructor'),getConstant('general__eventStaffCategorySubstitute')]:
                this_category = getConstant('financial__classInstructionExpenseCat')
            else:
                this_category = getConstant('financial__otherStaffExpenseCat')

            ExpenseItem.objects.create(eventstaffmember=member,category=this_category,description=expense_description,submissionUser=submissionUser,hours=hours_taught,wageRate=wage_rate)


def createRevenueItemsForRegistrations(request=None,datetimeTuple=None):

    if hasattr(request,'user'):
        submissionUser = request.user
    else:
        submissionUser = None

    this_category = getConstant('financial__registrationsRevenueCat')

    filters_events = {'revenueitem__isnull': True,'finalEventRegistration__isnull': False}

    if datetimeTuple:
        timelist = list(datetimeTuple)
        timelist.sort()

        filters_events['finalEventRegistration__event__eventoccurrence__startTime__gte'] = timelist[0]
        filters_events['finalEventRegistration__event__eventoccurrence__startTime__lte'] = timelist[1]
    else:
        c = getConstant('financial__autoGenerateRevenueRegistrationsWindow') or 0
        if c > 0:
            filters_events['finalEventRegistration__event__eventoccurrence__startTime__gte'] = timezone.now() - relativedelta(months=c)

    for item in InvoiceItem.objects.filter(**filters_events).distinct():
        if item.finalRegistration.paidOnline:
            received = True
        else:
            received = False

        revenue_description = _('Event Registration ') + str(item.finalEventRegistration.id) + ': ' + item.invoice.finalRegistration.fullName
        RevenueItem.objects.create(invoiceItem=item,category=this_category,description=revenue_description,submissionUser=submissionUser,grossTotal=item.grossTotal,total=item.total,received=received,receivedDate=item.invoice.modifiedDate)


def prepareFinancialStatement(year=None):

    if year:
        filter_year = year
    else:
        filter_year = timezone.now().year

    expenses_ytd = list(ExpenseItem.objects.filter(accrualDate__year=filter_year).aggregate(Sum('total')).values())[0]
    revenues_ytd = list(RevenueItem.objects.filter(accrualDate__year=filter_year).aggregate(Sum('total')).values())[0]
    expenses_awaiting_approval = list(ExpenseItem.objects.filter(approved=False,paid=False).aggregate(Sum('total')).values())[0]
    expenses_awaiting_payment = list(ExpenseItem.objects.filter(approved=True,paid=False).aggregate(Sum('total')).values())[0]
    expenses_paid_notapproved = list(ExpenseItem.objects.filter(approved=False,paid=True).aggregate(Sum('total')).values())[0]

    return {
        'expenses_ytd': expenses_ytd,
        'revenues_ytd': revenues_ytd,
        'expenses_awaiting_approval': expenses_awaiting_approval,
        'expenses_awaiting_payment': expenses_awaiting_payment,
        'expenses_paid_notapproved': expenses_paid_notapproved,
    }


def prepareStatementByMonth(**kwargs):
    basis = kwargs.get('basis')
    if basis not in EXPENSE_BASES.keys():
        basis = 'accrualDate'

    rev_basis = basis
    if rev_basis in ['paymentDate','approvalDate']:
        rev_basis = 'receivedDate'

    start_date = kwargs.get('start_date')
    end_date = kwargs.get('end_date')
    year = kwargs.get('year')

    # In order to provide major calculations, it's easiest to just get all the Expense and Revenue line items at once
    # To avoid too many unnecessary calls, be sure to filter off these querysets rather than pulling them again.
    expenseitems = ExpenseItem.objects.select_related('event').annotate(year=ExtractYear(basis,'year'),month=ExtractMonth(basis))
    revenueitems = RevenueItem.objects.select_related('event').annotate(year=ExtractYear(rev_basis,'year'),month=ExtractMonth(rev_basis))

    timeFilters = {}
    rev_timeFilters = {}
    if start_date:
        timeFilters['%s__gte' % basis] = start_date
        rev_timeFilters['%s__gte' % rev_basis] = start_date
    if end_date:
        timeFilters['%s__lt' % basis] = end_date
        rev_timeFilters['%s__lt' % rev_basis] = end_date

    if year and not (start_date or end_date):
        start_limit = ensure_timezone(datetime(year,1,1))
        end_limit = ensure_timezone(datetime(year + 1,1,1))

        timeFilters['%s__gte' % basis] = start_limit
        rev_timeFilters['%s__gte' % rev_basis] = start_limit
        timeFilters['%s__lt' % basis] = end_limit
        rev_timeFilters['%s__lt' % rev_basis] = end_limit

    if timeFilters:
        expenseitems = expenseitems.filter(**timeFilters)
        revenueitems = revenueitems.filter(**rev_timeFilters)

    # Get the set of possible month tuples.  If we are not given a date window, default to the last 12 months.
    allMonths = [(x.year,x.month) for x in revenueitems.dates(rev_basis,'month')]
    allMonths.sort(reverse=True)

    paginator = Paginator(allMonths,kwargs.get('paginate_by',50))
    try:
        paged_months = paginator.page(kwargs.get('page',1))
    except PageNotAnInteger:
        if kwargs.get('page') == 'last':
            paged_months = paginator.page(paginator.num_pages)
        else:
            paged_months = paginator.page(1)
    except EmptyPage:
        paged_months = paginator.page(paginator.num_pages)

    # Get everything by month in one query each, then pull from this.
    totalExpensesByMonth = expenseitems.values_list('year','month').annotate(Sum('total'),Sum('adjustments'),Sum('fees')).order_by('-year','-month')
    instructionExpensesByMonth = expenseitems.filter(category__in=[getConstant('financial__classInstructionExpenseCat'),getConstant('financial__assistantClassInstructionExpenseCat')]).values_list('year','month').annotate(Sum('total'),Sum('adjustments'),Sum('fees')).order_by('-year','-month')
    venueExpensesByMonth = expenseitems.filter(category=getConstant('financial__venueRentalExpenseCat')).values_list('year','month').annotate(Sum('total'),Sum('adjustments'),Sum('fees')).order_by('-year','-month')
    totalRevenuesByMonth = revenueitems.values_list('year','month').annotate(Sum('total'),Sum('adjustments'),Sum('fees')).order_by('-year','-month')

    # This includes only registrations in which a series was registered for (and was not cancelled)
    registrationsByMonth = Registration.objects.filter(eventregistration__cancelled=False).annotate(year=ExtractYear('dateTime'),month=ExtractMonth('dateTime')).values_list('year','month').annotate(count=Count('id')).order_by('-year','-month')

    # This little helper function avoids 0-item list issues and encapsulates the
    # needed list iterator for readability
    def valueOf(resultset,month,values=1):
        this = [x[2:(2 + values)] for x in resultset if x[0] == month[0] and x[1] == month[1]]
        if this and values != 1:
            return this[0]
        elif this:
            return this[0][0]
        elif values != 1:
            return [0] * values
        else:
            return 0

    monthlyStatement = []

    for this_month in paged_months:
        thisMonthlyStatement = {}
        thisMonthlyStatement['month'] = this_month
        thisMonthlyStatement['month_name'] = month_name[this_month[1]] + ' ' + str(this_month[0])
        thisMonthlyStatement['month_date'] = datetime(this_month[0],this_month[1],1)

        revenueList = valueOf(totalRevenuesByMonth,this_month,values=3)
        thisMonthlyStatement['revenues'] = revenueList[0] + revenueList[1] - revenueList[2]

        totalExpenseList = valueOf(totalExpensesByMonth,this_month,values=3)
        instructionExpenseList = valueOf(instructionExpensesByMonth,this_month,values=3)
        venueExpenseList = valueOf(venueExpensesByMonth,this_month,values=3)

        thisMonthlyStatement['expenses'] = {
            'total': (totalExpenseList[0] or 0) + (totalExpenseList[1] or 0) - (totalExpenseList[2] or 0),
            'instruction': (instructionExpenseList[0] or 0) + (instructionExpenseList[1] or 0) - (instructionExpenseList[2] or 0),
            'venue': (venueExpenseList[0] or 0) + (venueExpenseList[1] or 0) - (venueExpenseList[2] or 0),
        }
        thisMonthlyStatement['expenses']['other'] = thisMonthlyStatement['expenses']['total'] - thisMonthlyStatement['expenses']['instruction'] - thisMonthlyStatement['expenses']['venue']

        thisMonthlyStatement['registrations'] = valueOf(registrationsByMonth,this_month)
        thisMonthlyStatement['net_profit'] = thisMonthlyStatement['revenues'] - thisMonthlyStatement['expenses']['total']
        monthlyStatement.append(thisMonthlyStatement)

    monthlyStatement.sort(key=lambda x: x['month'], reverse=True)

    # Return not just the statement, but also the paginator in the style of ListView's paginate_queryset()
    return (paginator, paged_months, monthlyStatement, paged_months.has_other_pages())


def prepareStatementByEvent(**kwargs):
    all_events = Event.objects.prefetch_related('expenseitem_set','expenseitem_set__category','revenueitem_set','revenueitem_set__category')

    start_date = kwargs.get('start_date')
    end_date = kwargs.get('end_date')
    year = kwargs.get('year')

    if start_date:
        all_events = all_events.filter(year__gte=start_date.year).exclude(year=start_date.year,month__lt=start_date.month)
    if end_date:
        all_events = all_events.filter(year__lte=end_date.year).exclude(year=end_date.year,month__gt=end_date.month)
    if year and not (start_date or end_date):
        all_events = all_events.filter(year=year)

    paginator = Paginator(all_events,kwargs.get('paginate_by',50))
    try:
        paged_events = paginator.page(kwargs.get('page',1))
    except PageNotAnInteger:
        if kwargs.get('page') == 'last':
            paged_events = paginator.page(paginator.num_pages)
        else:
            paged_events = paginator.page(1)
    except EmptyPage:
        paged_events = paginator.page(paginator.num_pages)

    statementByEvent = []

    for event in paged_events:
        this_event_statement = {}

        # Allows access of arbitrary properties
        this_event_statement['event'] = event
        if event.month:
            this_event_statement['month_name'] = '%s %s' % (month_name[event.month], event.year)
        else:
            this_event_statement['month_name'] = _('Unspecified Month')
        this_event_statement['event_name'] = event.name
        this_event_statement['registrations'] = {'total': event.numRegistered,}
        this_event_statement['registrations'].update(event.numRegisteredByRole)

        # The calculation of net vs. gross revenue for each registration item is done
        # in models.py via model methods.  Any discounts are applied equally to each event.
        event_revs = event.revenueitem_set.aggregate(Sum('grossTotal'),Sum('total'),Sum('adjustments'),Sum('fees'))

        this_event_statement['revenues'] = {
            'gross': event_revs['grossTotal__sum'] or 0,
            'netOfDiscounts': event_revs['total__sum'] or 0,
            'adjustments': event_revs['adjustments__sum'] or 0,
            'fees': event_revs['fees__sum'] or 0,
        }
        this_event_statement['revenues']['net'] = sum([this_event_statement['revenues']['netOfDiscounts'],
                                                       this_event_statement['revenues']['adjustments'],
                                                       -1 * this_event_statement['revenues']['fees']])

        this_event_statement['expenses'] = {
            'instruction': event.expenseitem_set.filter(category=getConstant('financial__classInstructionExpenseCat')).aggregate(Sum('total'))['total__sum'] or 0,
            'venue': event.expenseitem_set.filter(category=getConstant('financial__venueRentalExpenseCat')).aggregate(Sum('total'))['total__sum'] or 0,
            'other': event.expenseitem_set.exclude(category=getConstant('financial__venueRentalExpenseCat')).exclude(category=getConstant('financial__classInstructionExpenseCat')).aggregate(Sum('total'))['total__sum'] or 0,
            'fees': event.expenseitem_set.aggregate(Sum('fees'))['fees__sum'] or 0
        }
        this_event_statement['expenses']['total'] = sum([this_event_statement['expenses']['instruction'],
                                                         this_event_statement['expenses']['venue'],
                                                         this_event_statement['expenses']['other'],
                                                         this_event_statement['expenses']['fees']])
        this_event_statement['net_profit'] = this_event_statement['revenues']['net'] - this_event_statement['expenses']['total']

        statementByEvent.append(this_event_statement)

    # Return not just the statement, but also the paginator in the style of ListView's paginate_queryset()
    return (paginator, paged_events, statementByEvent, paged_events.has_other_pages())
