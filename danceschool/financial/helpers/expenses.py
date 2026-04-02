from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from danceschool.core.constants import getConstant
from danceschool.core.models import EventOccurrence, EventStaffMember
from danceschool.core.utils.timezone import ensure_timezone

from ..models import ExpenseItem, RepeatedExpenseRule, RoomRentalInfo, TransactionParty, ExpensePurpose


def getExpenseCategoryForStaffer(staffer=None, staffCategory=None):
    '''
    For standard categories of staff, map the EventStaffCategory to
    an ExpenseCategory using the stored constants.  Otherwise, the
    ExpenseCategory is a generic one.
    '''
    if staffer:
        staffCategory=staffer.category

    if staffCategory == getConstant('general__eventStaffCategoryAssistant'):
        return getConstant('financial__assistantClassInstructionExpenseCat')
    elif staffCategory in [
            getConstant('general__eventStaffCategoryInstructor'),
            getConstant('general__eventStaffCategorySubstitute')
    ]:
        return getConstant('financial__classInstructionExpenseCat')
    else:
        # This is the generic category for all Event staff, but it may be overridden below
        return getConstant('financial__otherStaffExpenseCat')


def addEventTimeFilters(
    event_timefilters=None, rule=None, datetimeTuple=None, event=None
):
    '''
    This function provides the filters needed to identify events for which an
    expense item may need to be generated.
    '''

    if not event_timefilters:
        event_timefilters = Q()

    c = getConstant('financial__autoGenerateEventExpensesWindow') or 30
    event_timefilters = event_timefilters & Q(
        event__endTime__gte=(timezone.now() - timedelta(days=c))
    )

    if datetimeTuple and len(datetimeTuple) == 2:
        timelist = list(datetimeTuple)
        timelist.sort()
        event_timefilters = event_timefilters & (
            Q(event__startTime__gte=timelist[0]) & Q(event__startTime__lte=timelist[1])
        )

    if event:
        event_timefilters = event_timefilters & Q(event__id=event.id)

    if rule:
        if rule.advanceDays is not None:
            if rule.advanceDaysReference == RepeatedExpenseRule.MilestoneChoices.end:
                event_timefilters = event_timefilters & \
                    Q(event__endTime__lte=timezone.now() + timedelta(days=rule.advanceDays))
            elif rule.advanceDaysReference == RepeatedExpenseRule.MilestoneChoices.start:
                event_timefilters = event_timefilters & \
                    Q(event__startTime__lte=timezone.now() + timedelta(days=rule.advanceDays))
        if rule.priorDays is not None:
            if rule.priorDaysReference == RepeatedExpenseRule.MilestoneChoices.end:
                event_timefilters = event_timefilters & \
                    Q(event__endTime__gte=timezone.now() - timedelta(days=rule.priorDays))
            elif rule.priorDaysReference == RepeatedExpenseRule.MilestoneChoices.start:
                event_timefilters = event_timefilters & \
                    Q(event__startTime__gte=timezone.now() - timedelta(days=rule.priorDays))
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

    return event_timefilters

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

    # Now, we loop through the set of rules that need to be applied, then loop through the
    # Events in the window in question that occurred at the location indicated by the rule.
    for rule in rulesToCheck:

        venue = (
            getattr(rule, 'location', None) if
            isinstance(rule, RoomRentalInfo) else
            getattr(rule, 'location', None)
        )
        loc = getattr(venue, 'location') if isinstance(venue, RoomRentalInfo) else venue
        event_locfilter = Q(event__room=venue) if isinstance(venue, RoomRentalInfo) else Q(event__location=venue)

        # Find or create the TransactionParty associated with the location.
        loc_party = TransactionParty.objects.get_or_create(
            location=loc, defaults={'name': loc.name}
        )[0]

        event_timefilters = addEventTimeFilters(
            rule=rule, datetimeTuple=datetimeTuple, event=event
        )

        # For construction of expense descriptions
        replacements = {
            'type': _('Event/Series venue rental'),
            'of': _('of'),
            'location': venue.name,
            'for': _('for'),
        }

        # Loop through EventOccurrences for which there are not already directly
        # allocated expenses under this rule, and create new ExpenseItems for
        # them depending on whether the rule requires hourly expenses or
        # non-hourly ones to be generated.
        occurrences = EventOccurrence.objects.filter(
            event_locfilter & event_timefilters
        ).exclude(Q(related_expenses__item__expenseRule=rule)).select_related(
            'event', 'event__location', 'event__room'
        ).distinct()

        if rule.applyRateRule == rule.RateRuleChoices.hourly:
            for this_occ in occurrences:
                # Hourly expenses are always generated without checking for
                # overlapping windows, because the periods over which hourly expenses
                # are defined are disjoint.  However, hourly expenses are allocated
                # directly to events, so we just need to create expenses for any events
                # that do not already have an Expense Item generate under this rule.
                replacements['name'] = this_occ.event.name
                replacements['dates'] = this_occ.localStartTime.strftime('%Y-%m-%d')
                if (
                        this_occ.localStartTime.strftime('%Y-%m-%d') !=
                        this_occ.localEndTime.strftime('%Y-%m-%d')
                ):
                    replacements['dates'] += ' %s %s' % (
                        _('to'), this_occ.localEndTime.strftime('%Y-%m-%d')
                    )

                new_item = ExpenseItem.objects.create(
                    event=this_occ.event,
                    category=rental_category,
                    payTo=loc_party,
                    expenseRule=rule,
                    description=(
                        '%(type)s %(of)s %(location)s %(for)s: %(name)s, %(dates)s' %
                        replacements
                    ),
                    submissionUser=submissionUser,
                    total=this_occ.duration * rule.rentalRate,
                    accrualDate=this_occ.startTime,
                )

                # Record that this occurrence was the purpose of the
                # newly-generated expense item.
                ExpensePurpose.objects.create(
                    item=new_item,
                    purpose=this_occ
                )

                generate_count += 1
        else:
            # Non-hourly expenses are generated by constructing the time
            # intervals in which the occurrence occurs, and removing from that
            # interval any intervals in which an expense has already been
            # generated under this rule (so, for example, monthly rentals will
            # now show up multiple times). So, we just need to construct the set
            # of intervals for which to construct expenses
            intervals = [(x.localStartTime, x.localEndTime) for x in occurrences]
            remaining_intervals = rule.getWindowsAndTotals(
                intervals, remove_existing_overlaps=True
            )

            for startTime, endTime, total, description in remaining_intervals:
                replacements['when'] = description

                new_item, created = ExpenseItem.objects.get_or_create(
                    category=rental_category,
                    payTo=loc_party,
                    expenseRule=rule,
                    periodStart=startTime,
                    periodEnd=endTime,
                    defaults={
                        'description': '%(type)s %(of)s %(location)s %(for)s %(when)s' % replacements,
                        'submissionUser': submissionUser,
                        'total': total,
                        'accrualDate': startTime,
                    }
                )

                # Record that this occurrence was the purpose of the
                # newly-generated expense item.
                ExpensePurpose.objects.create(
                    item=new_item,
                    purpose=this_occ
                )

                if created:
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

        else:
            # We don't want to generate duplicate expenses when there is both a category-limited
            # rule and a non-limited rule for the same person, so we have to construct the list
            # of categories that are to be excluded if no category is specified by this rule.
            coveredCategories = list(staffMember.expenserules.filter(
                category__isnull=False).values_list('category__id', flat=True))
            eventstaff_filter = Q(staffMember=staffMember) & ~Q(category__id__in=coveredCategories)

        event_timefilters = addEventTimeFilters(
            rule=rule, datetimeTuple=datetimeTuple, event=event
        )

        # Loop through EventStaffMembers for which there are not already
        # directly allocated expenses under this rule, and create new
        # ExpenseItems for them depending on whether the rule requires hourly
        # expenses or non-hourly ones to be generated. Note: we don't prefetch
        # the event on purpose, because this ends up being a non-polymorphic
        # linkage, which means that subclass properties (like name) are not
        # correctly handled.
        staffers = EventStaffMember.objects.filter(
            eventstaff_filter & event_timefilters
        ).exclude(Q(related_expenses__item__expenseRule=rule)).select_related(
            'staffMember',
        ).prefetch_related('occurrences').distinct()

        if rule.applyRateRule == rule.RateRuleChoices.hourly:
            if getConstant('financial__autoGenerateExpensesEventStaff') == 'per_occurrence':
                # Per-occurrence mode: create one ExpenseItem per staffer per
                # occurrence, with hours proportional to occurrence duration.
                # Re-query without the whole-staffer exclusion so we can check
                # at the individual occurrence level inside the loop.
                staffers_per_occ = EventStaffMember.objects.filter(
                    eventstaff_filter & event_timefilters
                ).select_related('staffMember').prefetch_related('occurrences').distinct()

                for staffer in staffers_per_occ:
                    allocation = staffer.allocationByOccurrence
                    relevant_occs = (
                        staffer.occurrences.filter(cancelled=False) or
                        staffer.event.eventoccurrence_set.filter(cancelled=False)
                    )

                    staffer_party = TransactionParty.objects.get_or_create(
                        staffMember=staffer.staffMember,
                        defaults={
                            'name': staffer.staffMember.fullName,
                            'user': getattr(staffer.staffMember, 'userAccount', None)
                        }
                    )[0]

                    for occ in relevant_occs:
                        # Skip if an expense already exists for this
                        # staffer + occurrence + rule combination.
                        if staffer.related_expenses.filter(
                            item__expenseRule=rule,
                            occurrence=occ,
                        ).exists():
                            continue

                        occ_hours = (
                            allocation.get((occ.id, staffer.event.id), {}).get('duration', 0) / 3600
                        )
                        if not occ_hours:
                            continue

                        replacements['event'] = staffer.event.name
                        replacements['name'] = staffer.staffMember.fullName
                        replacements['dates'] = occ.localStartTime.strftime('%Y-%m-%d')

                        new_item = ExpenseItem.objects.create(
                            event=staffer.event,
                            category=getExpenseCategoryForStaffer(staffer),
                            expenseRule=rule,
                            description='%(type)s %(to)s %(name)s %(for)s: %(event)s, %(dates)s' % replacements,
                            submissionUser=submissionUser,
                            hours=occ_hours,
                            wageRate=rule.rentalRate,
                            total=occ_hours * rule.rentalRate,
                            accrualDate=occ.startTime,
                            payTo=staffer_party,
                        )

                        ExpensePurpose.objects.create(
                            item=new_item,
                            purpose=staffer,
                            occurrence=occ,
                        )

                        generate_count += 1
            else:
                # Per-event mode (default): one ExpenseItem per EventStaffMember.
                for staffer in staffers:
                    # Hourly expenses are always generated without checking for
                    # overlapping windows, because the periods over which hourly
                    # expenses are defined are disjoint.  However, hourly expenses
                    # are allocated directly to events, so we just need to create
                    # expenses for any events that do not already have an Expense
                    # Item generated under this rule.
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
                        'category': getExpenseCategoryForStaffer(staffer),
                        'expenseRule': rule,
                        'description': '%(type)s %(to)s %(name)s %(for)s: %(event)s, %(dates)s' % replacements,
                        'submissionUser': submissionUser,
                        'hours': staffer.netHours,
                        'wageRate': rule.rentalRate,
                        'total': staffer.netHours * rule.rentalRate,
                        'accrualDate': staffer.event.startTime,
                        'payTo': staffer_party,
                    }

                    new_item = ExpenseItem.objects.create(**params)

                    # Record that this staffing was the purpose of the
                    # newly-generated expense item.
                    ExpensePurpose.objects.create(
                        item=new_item,
                        purpose=staffer
                    )

                    generate_count += 1
        else:
            # Non-hourly expenses are generated by constructing the time
            # intervals in which the occurrence occurs, and removing from that
            # interval any intervals in which an expense has already been
            # generated under this rule (so, for example, monthly rentals will
            # not show up multiple times). So, we just need to construct the set
            # of intervals for which to construct expenses. This is done
            # separately for each EventStaffMember instance so that we can keep
            # track of the full set of purposes of each expense.
            for staffer in staffers:

                expense_category=getExpenseCategoryForStaffer(staffer)

                # Find or create the TransactionParty associated with the staff member.
                staffer_party = TransactionParty.objects.get_or_create(
                    staffMember=staffer.staffMember,
                    defaults={
                        'name': staffer.staffMember.fullName,
                        'user': getattr(staffer.staffMember, 'userAccount', None)
                    }
                )[0]

                # Intervals are defined by the occurrences for which the
                # individual staffed, or by the full set of event occurrences
                # if no staffing-specific occurrences are specified.
                intervals = [
                    (x.localStartTime, x.localEndTime) for x in
                    (
                        staffer.occurrences.all() or
                        staffer.event.eventoccurrence_set.all()
                    )
                ]
                remaining_intervals = rule.getWindowsAndTotals(
                    intervals, remove_existing_overlaps=True,
                    category=expense_category, payTo=staffer_party
                )

                for startTime, endTime, total, description in remaining_intervals:
                    replacements['when'] = description
                    replacements['name'] = staffer.staffMember.fullName

                    new_item, created = ExpenseItem.objects.get_or_create(
                        category=expense_category,
                        payTo=staffer_party,
                        expenseRule=rule,
                        periodStart=startTime,
                        periodEnd=endTime,
                        defaults={
                            'description': '%(type)s %(to)s %(name)s %(for)s %(when)s' % replacements,
                            'submissionUser': submissionUser,
                            'total': total,
                            'accrualDate': startTime,
                        }
                    )

                    # Record that this staffing was the purpose of the
                    # newly-generated expense item.
                    ExpensePurpose.objects.create(
                        item=new_item,
                        purpose=staffer
                    )

                    if created:
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
