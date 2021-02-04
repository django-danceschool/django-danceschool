from django.conf import settings
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDate, TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import unicodecsv as csv
from calendar import month_name
import pytz

from danceschool.core.constants import getConstant
from danceschool.core.models import (
    Registration, Event, EventOccurrence, EventStaffMember, InvoiceItem, Room, StaffMember
)
from danceschool.core.utils.timezone import ensure_timezone

from .constants import EXPENSE_BASES
from .models import ExpenseItem, RevenueItem, RepeatedExpenseRule, RoomRentalInfo, TransactionParty


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


def createExpenseItemsForVenueRental(request=None, datetimeTuple=None, rule=None, event=None):
    '''
    For each Location or Room-related Repeated Expense Rule, look for Events
    in the designated time window that do not already have expenses associated
    with them.  For hourly rental expenses, then generate new expenses that are
    associated with this rule.  For non-hourly expenses, generate new expenses
    based on the non-overlapping intervals of days, weeks or months for which
    there is not already an ExpenseItem associated with the rule in question.
    '''

    # These are used repeatedly, so they are put at the top
    submissionUser = getattr(request, 'user', None)
    rental_category = getConstant('financial__venueRentalExpenseCat')

    # Return the number of new expense items created
    generate_count = 0

    # First, construct the set of rules that need to be checked for affiliated events
    rule_filters = Q(disabled=False) & Q(rentalRate__gt=0) & \
        (Q(locationrentalinfo__isnull=False) | Q(roomrentalinfo__isnull=False))
    if rule:
        rule_filters = rule_filters & Q(id=rule.id)
    rulesToCheck = RepeatedExpenseRule.objects.filter(rule_filters).distinct()

    # These are the filters place on Events that overlap the window in which
    # expenses are being generated.
    event_timefilters = Q()

    if datetimeTuple and len(datetimeTuple) == 2:
        timelist = list(datetimeTuple)
        timelist.sort()
        event_timefilters = event_timefilters & (
            Q(startTime__gte=timelist[0]) & Q(startTime__lte=timelist[1])
        )
    if event:
        event_timefilters = event_timefilters & Q(id=event.id)

    # Now, we loop through the set of rules that need to be applied, then loop through the
    # Events in the window in question that occurred at the location indicated by the rule.
    for rule in rulesToCheck:

        venue = (
            getattr(rule, 'location', None) if
            isinstance(rule, RoomRentalInfo) else
            getattr(rule, 'location', None)
        )
        loc = getattr(venue, 'location') if isinstance(venue, Room) else venue
        event_locfilter = Q(room=venue) if isinstance(venue, Room) else Q(location=venue)

        # Find or create the TransactionParty associated with the location.
        loc_party = TransactionParty.objects.get_or_create(
            location=loc, defaults={'name': loc.name}
        )[0]

        if rule.advanceDays:
            if rule.advanceDaysReference == RepeatedExpenseRule.MilestoneChoices.end:
                event_timefilters = event_timefilters & \
                    Q(endTime__lte=timezone.now() + timedelta(days=rule.advanceDays))
            elif rule.advanceDaysReference == RepeatedExpenseRule.MilestoneChoices.start:
                event_timefilters = event_timefilters & \
                    Q(startTime__lte=timezone.now() + timedelta(days=rule.advanceDays))
        if rule.priorDays:
            if rule.priorDaysReference == RepeatedExpenseRule.MilestoneChoices.end:
                event_timefilters = event_timefilters & \
                    Q(endTime__gte=timezone.now() - timedelta(days=rule.priorDays))
            elif rule.priorDaysReference == RepeatedExpenseRule.MilestoneChoices.start:
                event_timefilters = event_timefilters & \
                    Q(startTime__gte=timezone.now() - timedelta(days=rule.priorDays))
        if rule.startDate:
            event_timefilters = event_timefilters & Q(
                event__startTime__gte=timezone.now().replace(
                    year=rule.startDate.year, month=rule.startDate.month, day=rule.startDate.day,
                    hour=0, minute=0, second=0, microsecond=0,
                )
            )
        if rule.endDate:
            event_timefilters = event_timefilters & Q(
                event__startTime__lte=timezone.now().replace(
                    year=rule.endDate.year, month=rule.endDate.month, day=rule.endDate.day,
                    hour=0, minute=0, second=0, microsecond=0,
                )
            )

        # For construction of expense descriptions
        replacements = {
            'type': _('Event/Series venue rental'),
            'of': _('of'),
            'location': venue.name,
            'for': _('for'),
        }

        # Loop through Events for which there are not already directly allocated
        # expenses under this rule, and create new ExpenseItems for them depending
        # on whether the rule requires hourly expenses or non-hourly ones to
        # be generated.
        events = Event.objects.filter(event_locfilter & event_timefilters).exclude(
            Q(expenseitem__expenseRule=rule)).distinct()

        if rule.applyRateRule == rule.RateRuleChoices.hourly:
            for this_event in events:
                # Hourly expenses are always generated without checking for
                # overlapping windows, because the periods over which hourly expenses
                # are defined are disjoint.  However, hourly expenses are allocated
                # directly to events, so we just need to create expenses for any events
                # that do not already have an Expense Item generate under this rule.
                replacements['name'] = this_event.name
                replacements['dates'] = this_event.localStartTime.strftime('%Y-%m-%d')
                if (
                        event.localStartTime.strftime('%Y-%m-%d') !=
                        this_event.localEndTime.strftime('%Y-%m-%d')
                ):
                    replacements['dates'] += ' %s %s' % (
                        _('to'), this_event.localEndTime.strftime('%Y-%m-%d')
                    )

                ExpenseItem.objects.create(
                    event=this_event,
                    category=rental_category,
                    payTo=loc_party,
                    expenseRule=rule,
                    description=(
                        '%(type)s %(of)s %(location)s %(for)s: %(name)s, %(dates)s' %
                        replacements
                    ),
                    submissionUser=submissionUser,
                    total=this_event.duration * rule.rentalRate,
                    accrualDate=this_event.startTime,
                )
                generate_count += 1
        else:
            # Non-hourly expenses are generated by constructing the time
            # intervals in which the occurrence occurs, and removing from that
            # interval any intervals in which an expense has already been
            # generated under this rule (so, for example, monthly rentals will
            # now show up multiple times). So, we just need to construct the set
            # of intervals for which to construct expenses
            intervals = [
                (x.localStartTime, x.localEndTime) for x in
                EventOccurrence.objects.filter(event__in=events)
            ]
            remaining_intervals = rule.getWindowsAndTotals(intervals)

            for startTime, endTime, total, description in remaining_intervals:
                replacements['when'] = description

                ExpenseItem.objects.create(
                    category=rental_category,
                    payTo=loc_party,
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


def createExpenseItemsForEvents(request=None, datetimeTuple=None, rule=None, event=None):
    '''
    For each StaffMember-related Repeated Expense Rule, look for EventStaffMember
    instances in the designated time window that do not already have expenses associated
    with them.  For hourly rental expenses, then generate new expenses that are
    associated with this rule.  For non-hourly expenses, generate new expenses
    based on the non-overlapping intervals of days, weeks or months for which
    there is not already an ExpenseItem associated with the rule in question.
    '''

    # This is used repeatedly, so it is put at the top
    submissionUser = getattr(request, 'user', None)

    # Return the number of new expense items created
    generate_count = 0

    # First, construct the set of rules that need to be checked for affiliated events
    rule_filters = Q(disabled=False) & Q(rentalRate__gt=0) & \
        Q(Q(staffmemberwageinfo__isnull=False) | Q(staffdefaultwage__isnull=False))
    if rule:
        rule_filters = rule_filters & Q(id=rule.id)
    rulesToCheck = RepeatedExpenseRule.objects.filter(
        rule_filters).distinct().order_by(
            '-staffmemberwageinfo__category', '-staffdefaultwage__category'
        )

    # These are the filters placed on Events that overlap the window in which
    # expenses are being generated.
    event_timefilters = Q()

    if datetimeTuple and len(datetimeTuple) == 2:
        timelist = list(datetimeTuple)
        timelist.sort()
        event_timefilters = event_timefilters & (
            Q(event__startTime__gte=timelist[0]) & Q(event__startTime__lte=timelist[1])
        )

    if event:
        event_timefilters = event_timefilters & Q(event__id=event.id)

    # Now, we loop through the set of rules that need to be applied, then loop
    # through the Events in the window in question that involved the staff
    # member indicated by the rule.
    for rule in rulesToCheck:
        staffMember = getattr(rule, 'staffMember', None)
        staffCategory = getattr(rule, 'category', None)

        # No need to continue if expenses are not to be generated
        if (
                (not staffMember and not staffCategory) or
                (
                    not staffMember and not
                    getConstant('financial__autoGenerateFromStaffCategoryDefaults')
                )
        ):
            continue

        # For construction of expense descriptions
        replacements = {
            'type': _('Staff'),
            'to': _('payment to'),
            'for': _('for'),
        }

        # This is the generic category for all Event staff, but it may be overridden below
        expense_category = getConstant('financial__otherStaffExpenseCat')

        if staffCategory:
            if staffMember:
                # This staff member in this category
                eventstaff_filter = Q(staffMember=staffMember) & Q(category=staffCategory)
            elif getConstant('financial__autoGenerateFromStaffCategoryDefaults'):
                # Any staff member who does not already have a rule specified this category
                eventstaff_filter = (
                    Q(category=staffCategory) &
                    ~Q(staffMember__expenserules__category=staffCategory)
                )
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
                category__isnull=False).values_list('category__id', flat=True))
            eventstaff_filter = Q(staffMember=staffMember) & ~Q(category__id__in=coveredCategories)

        if rule.advanceDays is not None:
            if rule.advanceDaysReference == RepeatedExpenseRule.MilestoneChoices.end:
                event_timefilters = event_timefilters & Q(
                    event__endTime__lte=timezone.now() + timedelta(days=rule.advanceDays)
                )
            elif rule.advanceDaysReference == RepeatedExpenseRule.MilestoneChoices.start:
                event_timefilters = event_timefilters & Q(
                    event__startTime__lte=timezone.now() + timedelta(days=rule.advanceDays)
                )
        if rule.priorDays is not None:
            if rule.priorDaysReference == RepeatedExpenseRule.MilestoneChoices.end:
                event_timefilters = event_timefilters & Q(
                    event__endTime__gte=timezone.now() - timedelta(days=rule.priorDays)
                )
            elif rule.priorDaysReference == RepeatedExpenseRule.MilestoneChoices.start:
                event_timefilters = event_timefilters & Q(
                    event__startTime__gte=timezone.now() - timedelta(days=rule.priorDays)
                )
        if rule.startDate:
            event_timefilters = event_timefilters & Q(event__startTime__gte=timezone.now().replace(
                year=rule.startDate.year, month=rule.startDate.month, day=rule.startDate.day,
                hour=0, minute=0, second=0, microsecond=0,
            ))
        if rule.endDate:
            event_timefilters = event_timefilters & Q(event__startTime__lte=timezone.now().replace(
                year=rule.endDate.year, month=rule.endDate.month, day=rule.endDate.day,
                hour=0, minute=0, second=0, microsecond=0,
            ))

        # Loop through EventStaffMembers for which there are not already
        # directly allocated expenses under this rule, and create new
        # ExpenseItems for them depending on whether the rule requires hourly
        # expenses or non-hourly ones to be generated.

        staffers = EventStaffMember.objects.filter(eventstaff_filter & event_timefilters).exclude(
            Q(event__expenseitem__expenseRule=rule)).distinct()

        if rule.applyRateRule == rule.RateRuleChoices.hourly:
            for staffer in staffers:
                # Hourly expenses are always generated without checking for
                # overlapping windows, because the periods over which hourly
                # expenses are defined are disjoint.  However, hourly expenses
                # are allocated directly to events, so we just need to create
                # expenses for any events that do not already have an Expense
                # Item generate under this rule.
                replacements['event'] = staffer.event.name
                replacements['name'] = staffer.staffMember.fullName
                replacements['dates'] = staffer.event.localStartTime.strftime('%Y-%m-%d')
                if (
                        staffer.event.localStartTime.strftime('%Y-%m-%d') !=
                        staffer.event.localEndTime.strftime('%Y-%m-%d')
                ):
                    replacements['dates'] += ' %s %s' % (
                        _('to'), staffer.event.localEndTime.strftime('%Y-%m-%d')
                    )

                # Find or create the TransactionParty associated with the staff member.
                staffer_party = TransactionParty.objects.get_or_create(
                    staffMember=staffer.staffMember,
                    defaults={
                        'name': staffer.staffMember.fullName,
                        'user': getattr(staffer.staffMember, 'userAccount', None)
                    }
                )[0]

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
                    'payTo': staffer_party,
                }

                ExpenseItem.objects.create(**params)
                generate_count += 1
        else:
            # Non-hourly expenses are generated by constructing the time
            # intervals in which the occurrence occurs, and removing from that
            # interval any intervals in which an expense has already been
            # generated under this rule (so, for example, monthly rentals will
            # now show up multiple times). So, we just need to construct the set
            # of intervals for which to construct expenses.  We first need to
            # split the set of EventStaffMember objects by StaffMember (in case
            # this rule is not person-specific) and then run this provedure
            # separated by StaffMember.
            members = StaffMember.objects.filter(eventstaffmember__in=staffers)

            for member in members:
                events = [x.event for x in staffers.filter(staffMember=member)]

                # Find or create the TransactionParty associated with the staff member.
                staffer_party = TransactionParty.objects.get_or_create(
                    staffMember=member,
                    defaults={
                        'name': member.fullName,
                        'user': getattr(member, 'userAccount', None)
                    }
                )[0]

                intervals = [
                    (x.localStartTime, x.localEndTime) for x in
                    EventOccurrence.objects.filter(event__in=events)
                ]
                remaining_intervals = rule.getWindowsAndTotals(intervals)

                for startTime, endTime, total, description in remaining_intervals:
                    replacements['when'] = description
                    replacements['name'] = member.fullName

                    params = {
                        'category': expense_category,
                        'expenseRule': rule,
                        'periodStart': startTime,
                        'periodEnd': endTime,
                        'description': '%(type)s %(to)s %(name)s %(for)s %(when)s' % replacements,
                        'submissionUser': submissionUser,
                        'total': total,
                        'accrualDate': startTime,
                        'payTo': staffer_party,
                    }

                    ExpenseItem.objects.create(**params)
                    generate_count += 1
    rulesToCheck.update(lastRun=timezone.now())
    return generate_count


def createGenericExpenseItems(request=None, datetimeTuple=None, rule=None):
    '''
    Generic repeated expenses are created by just entering an
    expense at each exact point specified by the rule, without
    regard for whether events are scheduled in the specified
    window,
    '''

    # These are used repeatedly, so they are put at the top
    submissionUser = getattr(request, 'user', None)

    # Return the number of new expense items created
    generate_count = 0

    # First, construct the set of rules that need to be checked for affiliated events
    rule_filters = Q(disabled=False) & Q(rentalRate__gt=0) & \
        Q(genericrepeatedexpense__isnull=False)
    if rule:
        rule_filters = rule_filters & Q(id=rule.id)
    rulesToCheck = RepeatedExpenseRule.objects.filter(rule_filters).distinct()

    # These are the filters place on Events that overlap the window in which
    # expenses are being generated.
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
            limits[1] = min(limits[1], timezone.now() + timedelta(days=rule.advanceDays))
        if rule.priorDays:
            limits[0] = max(limits[0], timezone.now() - timedelta(days=rule.priorDays))

        if rule.startDate:
            limits[0] = max(
                limits[0],
                timezone.now().replace(
                    year=rule.startDate.year, month=rule.startDate.month, day=rule.startDate.day,
                    hour=0, minute=0, second=0, microsecond=0,
                )
            )
        if rule.endDate:
            limits[1] = min(
                limits[1],
                timezone.now().replace(
                    year=rule.endDate.year, month=rule.endDate.month, day=rule.endDate.day,
                    hour=0, minute=0, second=0, microsecond=0,
                )
            )

        # Find the first start time greater than the lower bound time.
        if rule.applyRateRule == RepeatedExpenseRule.RateRuleChoices.hourly:
            this_time = limits[0].replace(minute=0, second=0, microsecond=0)
            if this_time < limits[0]:
                this_time += timedelta(hours=1)
        elif rule.applyRateRule == RepeatedExpenseRule.RateRuleChoices.daily:
            this_time = limits[0].replace(hour=rule.dayStarts, minute=0, second=0, microsecond=0)
            if this_time < limits[0]:
                this_time += timedelta(days=1)
        elif rule.applyRateRule == RepeatedExpenseRule.RateRuleChoices.weekly:
            offset = limits[0].weekday() - rule.weekStarts
            this_time = limits[0].replace(
                day=limits[0].day - offset, hour=rule.dayStarts, minute=0, second=0, microsecond=0
            )
            if this_time < limits[0]:
                this_time += timedelta(days=7)
        else:
            this_time = limits[0].replace(
                day=rule.monthStarts, hour=rule.dayStarts, minute=0, second=0, microsecond=0
            )
            if this_time < limits[0]:
                this_time += relativedelta(months=1)

        while this_time <= limits[1]:
            defaults_dict = {
                'category': rule.category,
                'description': rule.name,
                'submissionUser': submissionUser,
                'total': rule.rentalRate,
                'accrualDate': this_time,
                'payTo': rule.payTo,
                'approved': str(_('Approved')) if rule.markApproved else None,
                'paid': rule.markPaid,
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


def prepareFinancialStatement(year=None):

    if year:
        filter_year = year
    else:
        filter_year = timezone.now().year

    expenses_ytd = list(
        ExpenseItem.objects.filter(accrualDate__year=filter_year).aggregate(Sum('total')).values()
    )[0]
    revenues_ytd = list(
        RevenueItem.objects.filter(accrualDate__year=filter_year).aggregate(Sum('total')).values()
    )[0]
    expenses_awaiting_approval = list(
        ExpenseItem.objects.filter(
            Q(paid=False) & (Q(approved__isnull=True) | Q(approved__exact=''))
        ).aggregate(Sum('total')).values()
    )[0]
    expenses_awaiting_payment = list(
        ExpenseItem.objects.filter(
            Q(paid=False) & ~(Q(approved__isnull=True) | Q(approved__exact=''))
        ).aggregate(Sum('total')).values()
    )[0]
    expenses_paid_notapproved = list(
        ExpenseItem.objects.filter(
            Q(paid=True) & (Q(approved__isnull=True) | Q(approved__exact=''))
        ).aggregate(Sum('total')).values()
    )[0]

    return {
        'expenses_ytd': expenses_ytd,
        'revenues_ytd': revenues_ytd,
        'expenses_awaiting_approval': expenses_awaiting_approval,
        'expenses_awaiting_payment': expenses_awaiting_payment,
        'expenses_paid_notapproved': expenses_paid_notapproved,
    }


def prepareStatementByPeriod(**kwargs):
    basis = kwargs.get('basis')
    if basis not in EXPENSE_BASES.keys():
        basis = 'accrualDate'

    rev_basis = basis
    if rev_basis in ['paymentDate', 'approvalDate']:
        rev_basis = 'receivedDate'

    # Used to filter the set of observations shown
    start_date = kwargs.get('start_date')
    end_date = kwargs.get('end_date')
    year = kwargs.get('year')

    # Needed to ensure that everything is in local time.
    localTimeZone = None
    if getattr(settings, 'TIME_ZONE', None):
        localTimeZone = pytz.timezone(getattr(settings, 'TIME_ZONE'))

    # Currently supported period types include month and date.  The variables
    # values, annotations, and order_by are used repeatedly for constructing
    # queries.
    period_type = kwargs.get('type', 'month')
    values = ('basisDate', )
    order_by = ('-basisDate', )

    def date_for_month(*args, **kwargs):
        return TruncDate(TruncMonth(*args, **kwargs))

    # NOTE: Django 2.1 introduces "TruncWeek", which should be added to the
    # options once the project requires Django 2.1.
    if period_type == 'month':
        DateFunc = date_for_month
    elif period_type == 'date':
        DateFunc = TruncDate
    else:
        raise ValueError(_('Invalid period type passed as kwarg.'))

    time_annotations = {'basisDate': DateFunc(basis, tzinfo=localTimeZone)}
    rev_time_annotations = {'basisDate': DateFunc(rev_basis, tzinfo=localTimeZone)}
    reg_time_annotations = {
        'basisDate': DateFunc(
            'eventregistration__event__startTime', tzinfo=localTimeZone
        )
    }

    timeFilters = {'%s__isnull' % basis: False}
    rev_timeFilters = {'%s__isnull' % rev_basis: False}
    if start_date:
        timeFilters['%s__gte' % basis] = start_date
        rev_timeFilters['%s__gte' % rev_basis] = start_date
    if end_date:
        timeFilters['%s__lt' % basis] = end_date
        rev_timeFilters['%s__lt' % rev_basis] = end_date

    if year and not (start_date or end_date):
        start_limit = ensure_timezone(datetime(year, 1, 1))
        end_limit = ensure_timezone(datetime(year + 1, 1, 1))

        timeFilters['%s__gte' % basis] = start_limit
        rev_timeFilters['%s__gte' % rev_basis] = start_limit
        timeFilters['%s__lt' % basis] = end_limit
        rev_timeFilters['%s__lt' % rev_basis] = end_limit

    # In order to provide major calculations, it's easiest to just get all the
    # Expense and Revenue line items at once To avoid too many unnecessary
    # calls, be sure to filter off these querysets rather than pulling them
    # again.
    expenseitems = ExpenseItem.objects.select_related('event').annotate(
        **time_annotations
    ).filter(**timeFilters)
    revenueitems = RevenueItem.objects.select_related('event').annotate(
        **rev_time_annotations
    ).filter(**rev_timeFilters)

    # Get the set of possible dates or months.
    all_periods_set = set()

    for qs in [expenseitems, revenueitems]:
        all_periods_set.update(list(
            qs.order_by().values('basisDate').annotate(n=Count('pk')).values_list('basisDate')
        ))

    all_periods = [x[0] for x in all_periods_set]
    all_periods.sort(reverse=True)

    paginator = Paginator(all_periods, kwargs.get('paginate_by', 50))
    try:
        paged_periods = paginator.page(kwargs.get('page', 1))
    except PageNotAnInteger:
        if kwargs.get('page') == 'last':
            paged_periods = paginator.page(paginator.num_pages)
        else:
            paged_periods = paginator.page(1)
    except EmptyPage:
        paged_periods = paginator.page(paginator.num_pages)

    # Define common annotations used repeatedly in queries.
    sum_annotations = (Sum('total'), Sum('adjustments'), Sum('fees'))

    # Get everything by month in one query each, then pull from this.
    totalExpensesByPeriod = expenseitems.values(*values).annotate(
        *sum_annotations
    ).order_by(*order_by)

    instructionExpensesByPeriod = expenseitems.filter(
        category__in=[
            getConstant('financial__classInstructionExpenseCat'),
            getConstant('financial__assistantClassInstructionExpenseCat')
        ]
    ).values(*values).annotate(*sum_annotations).order_by(*order_by)

    venueExpensesByPeriod = expenseitems.filter(
        category=getConstant('financial__venueRentalExpenseCat')
    ).values(*values).annotate(*sum_annotations).order_by(*order_by)

    totalRevenuesByPeriod = revenueitems.values(*values).annotate(
        *sum_annotations
    ).order_by(*order_by)

    # This includes only registrations in which a series was registered for (and was not cancelled)
    registrationsByPeriod = Registration.objects.filter(
        eventregistration__cancelled=False
    ).annotate(
        **reg_time_annotations
    ).values(*values).annotate(count=Count('id')).order_by(*order_by)

    periodStatement = []

    for this_period in paged_periods:
        thisPeriodStatement = {}
        thisPeriodStatement['period'] = this_period
        this_period_date = datetime.combine(this_period, datetime.min.time())

        if period_type == 'month':
            thisPeriodStatement.update({
                'period_date': this_period_date,
                'period_name': this_period_date.strftime('%B %Y'),
            })
        elif period_type == 'date':
            thisPeriodStatement.update({
                'period_date': this_period_date,
                'period_name': this_period.strftime('%b. %-d, %Y'),
            })

        def get_net(this_dict):
            '''
            Convenience function to calculate net value incorporating adjustments and fees.
            '''
            if not isinstance(this_dict, dict):
                this_dict = {}
            return this_dict.get('total__sum', 0) + \
                this_dict.get('adjustments__sum', 0) - \
                this_dict.get('fees__sum', 0)

        thisPeriodStatement['revenues'] = get_net(
            totalRevenuesByPeriod.filter(basisDate=this_period).first()
        )
        thisPeriodStatement['expenses'] = {
            'total': get_net(totalExpensesByPeriod.filter(basisDate=this_period).first()),
            'instruction': get_net(
                instructionExpensesByPeriod.filter(basisDate=this_period).first()
            ),
            'venue': get_net(
                venueExpensesByPeriod.filter(basisDate=this_period).first()
            ),
        }
        thisPeriodStatement['expenses']['other'] = (
            thisPeriodStatement['expenses']['total'] -
            thisPeriodStatement['expenses']['instruction'] -
            thisPeriodStatement['expenses']['venue']
        )

        thisPeriodStatement['registrations'] = (
            registrationsByPeriod.filter(basisDate=this_period).first() or {}
        ).get('count', 0)
        thisPeriodStatement['net_profit'] = (
            thisPeriodStatement['revenues'] - thisPeriodStatement['expenses']['total']
        )
        periodStatement.append(thisPeriodStatement)

    periodStatement.sort(key=lambda x: x['period_date'], reverse=True)

    # Return not just the statement, but also the paginator in the style of
    # ListView's paginate_queryset()
    return (paginator, paged_periods, periodStatement, paged_periods.has_other_pages())


def prepareStatementByEvent(**kwargs):
    all_events = Event.objects.prefetch_related(
        'expenseitem_set', 'expenseitem_set__category',
        'revenueitem_set', 'revenueitem_set__category'
    )

    start_date = kwargs.get('start_date')
    end_date = kwargs.get('end_date')
    year = kwargs.get('year')

    if start_date:
        all_events = all_events.filter(year__gte=start_date.year).exclude(
            year=start_date.year, month__lt=start_date.month
        )
    if end_date:
        all_events = all_events.filter(year__lte=end_date.year).exclude(
            year=end_date.year, month__gt=end_date.month
        )
    if year and not (start_date or end_date):
        all_events = all_events.filter(year=year)

    paginator = Paginator(all_events, kwargs.get('paginate_by', 50))
    try:
        paged_events = paginator.page(kwargs.get('page', 1))
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
        this_event_statement['registrations'] = {'total': event.numRegistered, }
        this_event_statement['registrations'].update(event.numRegisteredByRole)

        # The calculation of net vs. gross revenue for each registration item is
        # done in models.py via model methods.  Any discounts are applied
        # equally to each event.
        event_revs = event.revenueitem_set.aggregate(
            Sum('grossTotal'), Sum('total'), Sum('adjustments'), Sum('fees')
        )

        this_event_statement['revenues'] = {
            'gross': event_revs['grossTotal__sum'] or 0,
            'netOfDiscounts': event_revs['total__sum'] or 0,
            'adjustments': event_revs['adjustments__sum'] or 0,
            'fees': event_revs['fees__sum'] or 0,
        }
        this_event_statement['revenues']['net'] = sum([
            this_event_statement['revenues']['netOfDiscounts'],
            this_event_statement['revenues']['adjustments'],
            -1 * this_event_statement['revenues']['fees']
        ])

        this_event_statement['expenses'] = {
            'instruction': event.expenseitem_set.filter(
                category=getConstant('financial__classInstructionExpenseCat')
            ).aggregate(Sum('total'))['total__sum'] or 0,
            'venue': event.expenseitem_set.filter(
                category=getConstant('financial__venueRentalExpenseCat')
            ).aggregate(Sum('total'))['total__sum'] or 0,
            'other': event.expenseitem_set.exclude(
                category=getConstant('financial__venueRentalExpenseCat')
            ).exclude(
                category=getConstant('financial__classInstructionExpenseCat')
            ).aggregate(Sum('total'))['total__sum'] or 0,
            'fees': event.expenseitem_set.aggregate(Sum('fees'))['fees__sum'] or 0
        }
        this_event_statement['expenses']['total'] = sum([
            this_event_statement['expenses']['instruction'],
            this_event_statement['expenses']['venue'],
            this_event_statement['expenses']['other'],
            this_event_statement['expenses']['fees']
        ])
        this_event_statement['net_profit'] = (
            this_event_statement['revenues']['net'] - this_event_statement['expenses']['total']
        )

        statementByEvent.append(this_event_statement)

    # Return not just the statement, but also the paginator in the style of
    # ListView's paginate_queryset()
    return (paginator, paged_events, statementByEvent, paged_events.has_other_pages())
