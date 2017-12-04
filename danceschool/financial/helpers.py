from django.db.models import Sum, Count, Q
from django.db.models.functions import ExtractYear, ExtractMonth
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import unicodecsv as csv
from calendar import month_name

from danceschool.core.constants import getConstant
from danceschool.core.models import Registration, Event, EventOccurrence, EventStaffMember, InvoiceItem, Room
from danceschool.core.utils.timezone import ensure_timezone, ensure_localtime

from .constants import EXPENSE_BASES
from .models import ExpenseItem, RevenueItem, RepeatedExpenseRule, RoomRentalInfo


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


def createExpenseItemsForVenueRental(request=None,datetimeTuple=None,rule=None):
    '''
    For each Location or Room-related Repeated Expense Rule, look for Events
    in the designated time window that do not already have expenses associated
    with them.  For hourly rental expenses, then generate new expenses that are
    associated with this rule.  For non-hourly expenses, generate new expenses
    based on the non-overlapping intervals of days, weeks or months for which
    there is not already an ExpenseItem associated with the rule in question.
    '''

    # These are used repeatedly, so they are put at the top
    submissionUser = getattr(request,'user',None)
    rental_category = getConstant('financial__venueRentalExpenseCat')

    # Return the number of new expense items created
    generate_count = 0

    # First, construct the set of rules that need to be checked for affiliated events
    rule_filters = Q(disabled=False) & Q(rentalRate__gt=0) & \
        (Q(locationrentalinfo__isnull=False) | Q(roomrentalinfo__isnull=False))
    if rule:
        rule_filters = rule_filters & Q(id=rule.id)
    rulesToCheck = RepeatedExpenseRule.objects.filter(rule_filters).distinct()

    # These are the filters place on Events that overlap the window in which expenses are being generated.
    if datetimeTuple and len(datetimeTuple) == 2:
        timelist = list(datetimeTuple)
        timelist.sort()
        event_timefilters = Q(startTime__gte=timelist[0]) & Q(startTime__lte=timelist[1])
    else:
        event_timefilters = Q()

    # Now, we loop through the set of rules that need to be applied, then loop through the
    # Events in the window in question that occurred at the location indicated by the rule.
    for rule in rulesToCheck:

        venue = getattr(rule, 'location', None) if isinstance(rule,RoomRentalInfo) else getattr(rule, 'location', None)
        loc = getattr(venue,'location') if isinstance(venue,Room) else venue
        event_locfilter = Q(room=venue) if isinstance(venue,Room) else Q(location=venue)

        if rule.advanceDays:
            if rule.advanceDaysReference == RepeatedExpenseRule.MilestoneChoices.end:
                event_timefilters = event_timefilters & Q(endTime__lte=timezone.now() + timedelta(days=rule.advanceDays))
            elif rule.advanceDaysReference == RepeatedExpenseRule.MilestoneChoices.start:
                event_timefilters = event_timefilters & Q(startTime__lte=timezone.now() + timedelta(days=rule.advanceDays))
        if rule.priorDays:
            if rule.priorDaysReference == RepeatedExpenseRule.MilestoneChoices.end:
                event_timefilters = event_timefilters & Q(endTime__gte=timezone.now() - timedelta(days=rule.priorDays))
            elif rule.priorDaysReference == RepeatedExpenseRule.MilestoneChoices.start:
                event_timefilters = event_timefilters & Q(startTime__gte=timezone.now() - timedelta(days=rule.priorDays))
        if rule.startDate:
            event_timefilters = event_timefilters & Q(event__startTime__gte=timezone.now().replace(
                year=rule.startDate.year,month=rule.startDate.month,day=rule.startDate.day,
                hour=0,minute=0,second=0,microsecond=0,
            ))
        if rule.endDate:
            event_timefilters = event_timefilters & Q(event__startTime__lte=timezone.now().replace(
                year=rule.endDate.year,month=rule.endDate.month,day=rule.endDate.day,
                hour=0,minute=0,second=0,microsecond=0,
            ))

        # For construction of expense descriptions
        replacements = {
            'type': _('Event/Series venue rental'),
            'of': _('of'),
            'location': venue.name,
            'for': _('for'),
        }

        # Loop through Events for which there are not already directly allocated expenses under this rule,
        # and create new ExpenseItems for them depending on whether the rule requires hourly expenses or
        # non-hourly ones to be generated.
        events = Event.objects.filter(event_locfilter & event_timefilters).exclude(
            Q(expenseitem__expenseRule=rule)).distinct()

        if rule.applyRateRule == rule.RateRuleChoices.hourly:
            for event in events:
                # Hourly expenses are always generated without checking for overlapping windows, because
                # the periods over which hourly expenses are defined are disjoint.  However, hourly expenses
                # are allocated directly to events, so we just need to create expenses for any events
                # that do not already have an Expense Item generate under this rule.
                replacements['name'] = event.name
                replacements['dates'] = event.startTime.strftime('%Y-%m-%d')
                if event.startTime.strftime('%Y-%m-%d') != event.endTime.strftime('%Y-%m-%d'):
                    replacements['dates'] += ' %s %s' % (_('to'),event.endTime.strftime('%Y-%m-%d'))

                ExpenseItem.objects.create(
                    event=event,
                    category=rental_category,
                    payToLocation=loc,
                    expenseRule=rule,
                    description='%(type)s %(of)s %(location)s %(for)s: %(name)s, %(dates)s' % replacements,
                    submissionUser=submissionUser,
                    total=event.duration * rule.rentalRate,
                    accrualDate=event.startTime,
                )
                generate_count += 1
        else:
            # Non-hourly expenses are generated by constructing the time intervals in which the occurrence
            # occurs, and removing from that interval any intervals in which an expense has already been
            # generated under this rule (so, for example, monthly rentals will now show up multiple times).
            # So, we just need to construct the set of intervals for which to construct expenses
            intervals = [(ensure_localtime(x.startTime), ensure_localtime(x.endTime)) for x in EventOccurrence.objects.filter(event__in=events)]
            remaining_intervals = rule.getWindowsAndTotals(intervals)

            for startTime, endTime, total, description in remaining_intervals:
                replacements['when'] = description

                ExpenseItem.objects.create(
                    category=rental_category,
                    payToLocation=loc,
                    expenseRule=rule,
                    periodStart=startTime,
                    periodEnd=endTime,
                    description='%(type)s %(of)s %(location)s %(for)s %(when)s' % replacements,
                    submissionUser=submissionUser,
                    total=total,
                    accrualDate=startTime,
                )
                generate_count += 1
    rulesToCheck.update(lastRun=timezone.now())
    return generate_count


def createExpenseItemsForEvents(request=None,datetimeTuple=None,rule=None):
    '''
    For each StaffMember-related Repeated Expense Rule, look for EventStaffMember
    instances in the designated time window that do not already have expenses associated
    with them.  For hourly rental expenses, then generate new expenses that are
    associated with this rule.  For non-hourly expenses, generate new expenses
    based on the non-overlapping intervals of days, weeks or months for which
    there is not already an ExpenseItem associated with the rule in question.
    '''

    # This is used repeatedly, so it is put at the top
    submissionUser = getattr(request,'user',None)

    # Return the number of new expense items created
    generate_count = 0

    # First, construct the set of rules that need to be checked for affiliated events
    rule_filters = Q(disabled=False) & Q(rentalRate__gt=0) & \
        Q(staffmemberwageinfo__isnull=False)
    if rule:
        rule_filters = rule_filters & Q(id=rule.id)
    rulesToCheck = RepeatedExpenseRule.objects.filter(
        rule_filters).distinct().order_by('-staffmemberwageinfo__category')

    # These are the filters placed on Events that overlap the window in which expenses are being generated.
    if datetimeTuple and len(datetimeTuple) == 2:
        timelist = list(datetimeTuple)
        timelist.sort()
        event_timefilters = Q(event__startTime__gte=timelist[0]) & Q(event__startTime__lte=timelist[1])
    else:
        event_timefilters = Q()

    # Now, we loop through the set of rules that need to be applied, then loop through the
    # Events in the window in question that involved the staff member indicated by the rule.
    for rule in rulesToCheck:
        staffMember = rule.staffMember
        staffCategory = getattr(rule,'category',None)

        if not staffMember:
            continue

        # For construction of expense descriptions
        replacements = {
            'type': _('Staff'),
            'to': _('payment to'),
            'name': staffMember.fullName,
            'for': _('for'),
        }

        # This is the generic category for all Event staff, but it may be overridden below
        expense_category = getConstant('financial__otherStaffExpenseCat')

        if staffCategory:
            eventstaff_filter = Q(staffMember=staffMember) & Q(category=staffCategory)
            replacements['type'] = staffCategory.name

            # For standard categories of staff, map the EventStaffCategory to
            # an ExpenseCategory using the stored constants.  Otherwise, the
            # ExpenseCategory is a generic one.
            if staffCategory == getConstant('general__eventStaffCategoryAssistant'):
                expense_category = getConstant('financial__assistantClassInstructionExpenseCat')
            elif staffCategory in [
                getConstant('general__eventStaffCategoryInstructor'),
                getConstant('general__eventStaffCategorySubstitute')
            ]:
                expense_category = getConstant('financial__classInstructionExpenseCat')

        else:
            # We don't want to generate duplicate expenses when there is both a category-limited
            # rule and a non-limited rule for the same person, so we have to construct the list
            # of categories that are to be excluded if no category is specified by this rule.
            coveredCategories = list(staffMember.expenserules.filter(
                category__isnull=False).values_list('category__id',flat=True))
            eventstaff_filter = Q(staffMember=staffMember) & ~Q(category__id__in=coveredCategories)

        if rule.advanceDays is not None:
            if rule.advanceDaysReference == RepeatedExpenseRule.MilestoneChoices.end:
                event_timefilters = event_timefilters & Q(event__endTime__lte=timezone.now() + timedelta(days=rule.advanceDays))
            elif rule.advanceDaysReference == RepeatedExpenseRule.MilestoneChoices.start:
                event_timefilters = event_timefilters & Q(event__startTime__lte=timezone.now() + timedelta(days=rule.advanceDays))
        if rule.priorDays is not None:
            if rule.priorDaysReference == RepeatedExpenseRule.MilestoneChoices.end:
                event_timefilters = event_timefilters & Q(event__endTime__gte=timezone.now() - timedelta(days=rule.priorDays))
            elif rule.priorDaysReference == RepeatedExpenseRule.MilestoneChoices.start:
                event_timefilters = event_timefilters & Q(event__startTime__gte=timezone.now() - timedelta(days=rule.priorDays))
        if rule.startDate:
            event_timefilters = event_timefilters & Q(event__startTime__gte=timezone.now().replace(
                year=rule.startDate.year,month=rule.startDate.month,day=rule.startDate.day,
                hour=0,minute=0,second=0,microsecond=0,
            ))
        if rule.endDate:
            event_timefilters = event_timefilters & Q(event__startTime__lte=timezone.now().replace(
                year=rule.endDate.year,month=rule.endDate.month,day=rule.endDate.day,
                hour=0,minute=0,second=0,microsecond=0,
            ))

        # Loop through EventStaffMembers for which there are not already directly allocated expenses under this rule,
        # and create new ExpenseItems for them depending on whether the rule requires hourly expenses or
        # non-hourly ones to be generated.
        staffers = EventStaffMember.objects.filter(eventstaff_filter & event_timefilters).exclude(
            Q(event__expenseitem__expenseRule=rule)).distinct()

        if rule.applyRateRule == rule.RateRuleChoices.hourly:
            for staffer in staffers:
                # Hourly expenses are always generated without checking for overlapping windows, because
                # the periods over which hourly expenses are defined are disjoint.  However, hourly expenses
                # are allocated directly to events, so we just need to create expenses for any events
                # that do not already have an Expense Item generate under this rule.
                replacements['event'] = staffer.event.name
                replacements['dates'] = staffer.event.startTime.strftime('%Y-%m-%d')
                if staffer.event.startTime.strftime('%Y-%m-%d') != staffer.event.endTime.strftime('%Y-%m-%d'):
                    replacements['dates'] += ' %s %s' % (_('to'),staffer.event.endTime.strftime('%Y-%m-%d'))

                params = {
                    'event': staffer.event,
                    'category': expense_category,
                    'expenseRule': rule,
                    'description': '%(type)s %(to)s %(name)s %(for)s: %(event)s, %(dates)s' % replacements,
                    'submissionUser': submissionUser,
                    'hours': staffer.netHours,
                    'wageRate': rule.rentalRate,
                    'total': staffer.netHours * rule.rentalRate,
                    'accrualDate': staffer.event.startTime,
                }

                if getattr(staffMember,'userAccount',None):
                    params['payToUser'] = staffMember.userAccount
                else:
                    params['payToName'] = staffMember.fullName

                ExpenseItem.objects.create(**params)
                generate_count += 1
        else:
            # Non-hourly expenses are generated by constructing the time intervals in which the occurrence
            # occurs, and removing from that interval any intervals in which an expense has already been
            # generated under this rule (so, for example, monthly rentals will now show up multiple times).
            # So, we just need to construct the set of intervals for which to construct expenses
            events = [x.event for x in staffers]

            intervals = [(ensure_localtime(x.startTime), ensure_localtime(x.endTime)) for x in EventOccurrence.objects.filter(event__in=events)]
            remaining_intervals = rule.getWindowsAndTotals(intervals)

            for startTime, endTime, total, description in remaining_intervals:
                replacements['when'] = description

                params = {
                    'category': expense_category,
                    'expenseRule': rule,
                    'periodStart': startTime,
                    'periodEnd': endTime,
                    'description': '%(type)s %(to)s %(name)s %(for)s %(when)s' % replacements,
                    'submissionUser': submissionUser,
                    'total': total,
                    'accrualDate': startTime,
                }

                if getattr(staffMember,'userAccount',None):
                    params['payToUser'] = staffMember.userAccount
                else:
                    params['payToName'] = staffMember.fullName

                ExpenseItem.objects.create(**params)
                generate_count += 1
    rulesToCheck.update(lastRun=timezone.now())
    return generate_count


def createGenericExpenseItems(request=None,datetimeTuple=None,rule=None):
    '''
    Generic repeated expenses are created by just entering an
    expense at each exact point specified by the rule, without
    regard for whether events are scheduled in the specified
    window,
    '''

    # These are used repeatedly, so they are put at the top
    submissionUser = getattr(request,'user',None)

    # Return the number of new expense items created
    generate_count = 0

    # First, construct the set of rules that need to be checked for affiliated events
    rule_filters = Q(disabled=False) & Q(rentalRate__gt=0) & \
        Q(genericrepeatedexpense__isnull=False)
    if rule:
        rule_filters = rule_filters & Q(id=rule.id)
    rulesToCheck = RepeatedExpenseRule.objects.filter(rule_filters).distinct()

    # These are the filters place on Events that overlap the window in which expenses are being generated.
    if datetimeTuple and len(datetimeTuple) == 2:
        timelist = list(datetimeTuple)
        timelist.sort()
    else:
        timelist = None

    # Now, we loop through the set of rules that need to be applied, check for an
    # existing expense item at each point specified by the rule, and create a new
    # expense if one does not exist.
    for rule in rulesToCheck:

        limits = timelist or [ensure_timezone(datetime.min), ensure_timezone(datetime.max)]

        if rule.advanceDays:
            limits[1] = min(limits[1],timezone.now() + timedelta(days=rule.advanceDays))
        if rule.priorDays:
            limits[0] = max(limits[0],timezone.now() - timedelta(days=rule.priorDays))

        if rule.startDate:
            limits[0] = max(
                limits[0],
                timezone.now().replace(
                    year=rule.startDate.year,month=rule.startDate.month,day=rule.startDate.day,
                    hour=0,minute=0,second=0,microsecond=0,
                )
            )
        if rule.endDate:
            limits[1] = min(
                limits[1],
                timezone.now().replace(
                    year=rule.endDate.year,month=rule.endDate.month,day=rule.endDate.day,
                    hour=0,minute=0,second=0,microsecond=0,
                )
            )

        # Find the first start time greater than the lower bound time.
        if rule.applyRateRule == RepeatedExpenseRule.RateRuleChoices.hourly:
            this_time = limits[0].replace(minute=0,second=0,microsecond=0)
            if this_time < limits[0]:
                this_time += timedelta(hours=1)
        elif rule.applyRateRule == RepeatedExpenseRule.RateRuleChoices.daily:
            this_time = limits[0].replace(hour=rule.dayStarts,minute=0,second=0,microsecond=0)
            if this_time < limits[0]:
                this_time += timedelta(days=1)
        elif rule.applyRateRule == RepeatedExpenseRule.RateRuleChoices.weekly:
            offset = limits[0].weekday() - rule.weekStarts
            this_time = limits[0].replace(day=limits[0].day - offset, hour=rule.dayStarts,minute=0,second=0,microsecond=0)
            if this_time < limits[0]:
                this_time += timedelta(days=7)
        else:
            this_time = limits[0].replace(day=rule.monthStarts,hour=rule.dayStarts,minute=0,second=0,microsecond=0)
            if this_time < limits[0]:
                this_time += relativedelta(months=1)

        while this_time <= limits[1]:
            defaults_dict = {
                'category': rule.category,
                'description': rule.name,
                'submissionUser': submissionUser,
                'total': rule.rentalRate,
                'accrualDate': this_time,
                'payToUser': rule.payToUser,
                'payToLocation': rule.payToLocation,
                'payToName': rule.payToName,
            }
            item, created = ExpenseItem.objects.get_or_create(
                expenseRule=rule,
                periodStart=this_time,
                periodEnd=this_time,
                defaults=defaults_dict
            )
            if created:
                generate_count += 1
            if rule.applyRateRule == RepeatedExpenseRule.RateRuleChoices.hourly:
                this_time += timedelta(hours=1)
            elif rule.applyRateRule == RepeatedExpenseRule.RateRuleChoices.daily:
                this_time += timedelta(days=1)
            elif rule.applyRateRule == RepeatedExpenseRule.RateRuleChoices.weekly:
                this_time += timedelta(days=7)
            else:
                this_time += relativedelta(months=1)
    rulesToCheck.update(lastRun=timezone.now())
    return generate_count


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
