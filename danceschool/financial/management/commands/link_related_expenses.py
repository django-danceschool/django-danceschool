from django.core.management.base import BaseCommand
from django.db.models import Q, F
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from danceschool.core.constants import getConstant
from danceschool.core.models import EventOccurrence, EventStaffMember
from danceschool.financial.models import ExpensePurpose, ExpenseItem, RepeatedExpenseRule


class Command(BaseCommand):
    help = 'Identify and link expense purposes for existing expense items related to staffing and venues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--allow_hours_mismatch', action='store_true',
            help='Allow hours mismatch in linked staff expenses.'
        )
        parser.add_argument(
            '--verbose', action='store_true',
            help='Provide detailed information on generated linkages.'
        )

    def handle_venue_expenses(self, *args, **kwargs):
        elig_expenses = ExpenseItem.objects.filter(
            Q(expensepurpose__isnull=True) & (
                Q(expenseRule__locationrentalinfo__isnull=False) |
                Q(expenseRule__roomrentalinfo__isnull=False)
            )
        ).select_related(
            'expenseRule', 'expenseRule__locationrentalinfo',
            'expenseRule__roomrentalinfo', 'payTo', 'payTo__location', 'event'
        )

        mismatch_expenses = elig_expenses.exclude(
            Q(expenseRule__locationrentalinfo__location=F('payTo__location')) |
            Q(expenseRule__roomrentalinfo__room__location=F('payTo__location'))
        )

        for l in mismatch_expenses:
            self.stdout.write(
                'NOTE: Mismatch between transaction party and expense rule. Skipping expense #{}'.format(l.id)
            )

        elig_expenses = elig_expenses.exclude(id__in=mismatch_expenses)

        locationrentalinfo_ct = ContentType.objects.get(
            app_label='financial', model='locationrentalinfo'
        )
        roomrentalinfo_ct = ContentType.objects.get(
            app_label='financial', model='roomrentalinfo'
        )
        eventoccurrence_ct = ContentType.objects.get(
            app_label='core', model='eventoccurrence'
        )

        generated_purposes = 0

        for expense in elig_expenses:

            filters = Q()
            ct = expense.expenseRule.polymorphic_ctype

            if expense.event:
                filters = Q(event=expense.event)

            if expense.periodStart and expense.periodEnd:
                filters = filters & (
                    Q(startTime__lt=expense.periodEnd) &
                    Q(endTime__gt=expense.periodStart)
                )

            if ct == locationrentalinfo_ct:
                filters = filters & Q(event__location=expense.expenseRule.locationrentalinfo.location)
            elif ct == roomrentalinfo_ct:
                filters = filters & Q(event__room=expense.expenseRule.roomrentalinfo.room)

            purposes = EventOccurrence.objects.filter(filters)

            if not purposes:
                self.stdout.write(
                    'NOTE: Did not identify a clear purpose for expense {}.'.format(expense.id) +
                    ' You may wish to manually construct an ExpensePurpose for this ' +
                    'expense later to avoid the creation of duplicate expense items.'
                )

            if kwargs.get('verbose', False):
                self.stdout.write(
                    'Found {} occurrences matching the venue expense item #{}: {}'.format(
                        purposes.count(), expense.id, expense.descriptions
                    )
                )

            ExpensePurpose.objects.bulk_create([ExpensePurpose(
                    item=expense, object_id=o.id, content_type=eventoccurrence_ct
            ) for o in purposes])

            generated_purposes += purposes.count()

        self.stdout.write('Successfully generated {} expense purposes for {} expense items.'.format(
            generated_purposes, elig_expenses.count()
        ))

    def handle_staff_expenses(self, *args, **kwargs):
        allow_hours_mismatch = kwargs.get('allow_hours_mismatch', False)

        # First, construct the set of rules that need to be checked for affiliated
        # event staff. The ordering of these rules matters because staff member-
        # specific rules take precedence over more general rules, and
        # category-specific rules take precedence over catch-all rules.
        rulesToCheck = RepeatedExpenseRule.objects.filter(
            Q(staffmemberwageinfo__isnull=False) | Q(staffdefaultwage__isnull=False)        
        ).distinct().order_by(
            '-staffmemberwageinfo__category', '-staffdefaultwage__category'
        )

        eventstaffmember_ct = ContentType.objects.get(
            app_label='core', model='eventstaffmember'
        )

        generated_purposes = 0
        matched_staff_count = 0

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
                if kwargs.get('verbose', False):
                    self.stdout.write(
                        'NOTE: Unable to identify a staff or category target for rule #{}: {}.'.format(
                            rule.id, rule.ruleName
                        )
                    )
                continue

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

            event_timefilters = Q()

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

            # Loop through EventStaffMembers that are eligible under this rule, and
            # for which there is not yet any identified expense.
            staffers = EventStaffMember.objects.filter(
                eventstaff_filter & event_timefilters &
                Q(related_expenses__isnull=True)
            ).select_related(
                'staffMember', 'event',
            ).prefetch_related('occurrences').distinct()

            if kwargs.get('verbose', False):
                self.stdout.write(
                    'Identified {} event staffers subject to rule #{}: {}.'.format(
                        staffers.count(), rule.id, rule.ruleName
                    )
                )

            if rule.applyRateRule == rule.RateRuleChoices.hourly:
                for staffer in staffers:
                    # Hourly expenses are allocated directly to events, so we just
                    # need to link this staff members to any expenses 

                    this_staffer_items = ExpenseItem.objects.filter(
                        expenseRule=rule, payTo__staffMember=staffer.staffMember,
                        event=staffer.event, category=expense_category,
                    )
                    if not allow_hours_mismatch:
                        this_staffer_items = this_staffer_items.filter(
                            hours=staffer.netHours
                        )
                    this_count = this_staffer_items.count()

                    if kwargs.get('verbose', False):
                        self.stdout.write(
                            'Identified {} expense items for staffer #{}: {}.'.format(
                                this_count, staffer.id, staffer.__str__()
                            )
                        )

                    if this_count > 0:
                        ExpensePurpose.objects.bulk_create([
                            ExpensePurpose(
                                item=i, object_id=staffer.id,
                                content_type=eventstaffmember_ct
                            ) for i in
                            this_staffer_items
                        ])
                        matched_staff_count += 1
                        generated_purposes += this_count
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
                        intervals, remove_existing_overlaps=False
                    )

                    matched_this_staffer = False

                    for startTime, endTime, total, description in remaining_intervals:
                        ei = ExpenseItem.objects.filter(
                            expenseRule=rule, payTo__staffMember=staffer.staffMember,
                            category=expense_category, periodStart=startTime,
                            periodEnd=endTime
                        ).first()
                        if ei:
                            if kwargs.get('verbose', False):
                                self.stdout.write(
                                    'Identified expense item for interval ({}, {}) for staffer #{}: {}.'.format(
                                        startTime, endTime, staffer.id, staffer.__str__()
                                    )
                                )

                            ExpensePurpose.objects.create(
                                item=ei, object_id=staffer.id,
                                content_type=eventstaffmember_ct
                            )
                            generated_purposes += 1
                            if not matched_this_staffer:
                                matched_staff_count += 1
                                matched_this_staffer = True
                        elif kwargs.get('verbose', False):
                            self.stdout.write(
                                'Unable to identify expense item for interval ({}, {}) for staffer #{}: {}.'.format(
                                    startTime, endTime, staffer.id, staffer.__str__()
                                )
                            )

        self.stdout.write('Successfully generated {} expense purposes for {} staff members.'.format(
            generated_purposes, matched_staff_count
        ))


    def handle(self, *args, **options):
        '''
        All expenses associated with an expense rule that is not generic
        should be able to be associated with EventOccurrences or EventStaffMembers.
        '''

        # First, handle the venue expenses by linking to EventOccurrences.
        self.handle_venue_expenses(*args, **options)

        # First, handle the venue expenses by linking to EventOccurrences.
        self.handle_staff_expenses(*args, **options)

        self.stdout.write('Linkage of related expenses is complete.')






