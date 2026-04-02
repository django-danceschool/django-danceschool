from django.conf import settings
from django.db.models import Sum, Count, Q, Min
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.contenttypes.models import ContentType

from datetime import datetime
from dateutil.relativedelta import relativedelta
from calendar import month_name
import pytz

from danceschool.core.constants import getConstant
from danceschool.core.models import Registration, Event, EventOccurrence, EventStaffMember
from danceschool.core.utils.timezone import ensure_timezone, ensure_localtime

from ..constants import EXPENSE_BASES
from ..models import ExpenseItem, RevenueItem


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
    sum_annotations = (Sum('total'), Sum('adjustments'), Sum('fees'), Sum('net'))

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
            return this_dict.get('net__sum') or 0

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


def prepareStatementByEvent(paginate=True, **kwargs):
    all_events = Event.objects.prefetch_related(
        'expenseitem_set', 'expenseitem_set__category',
        'revenueitem_set', 'revenueitem_set__category',
        'eventoccurrence_set', 'eventoccurrence_set__related_expenses__item',
        'eventstaffmember_set', 'eventstaffmember_set__related_expenses__item',
    )

    # These are needed to allocate non-hourly expenses across events.
    eventoccurrence_ct = ContentType.objects.get_for_model(EventOccurrence).id
    eventstaffmember_ct = ContentType.objects.get_for_model(EventStaffMember).id

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


    if paginate:
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
    else:
        paged_events = all_events

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
            Sum('grossTotal'), Sum('total'), Sum('adjustments'), Sum('fees'), Sum('net')
        )

        this_event_statement['revenues'] = {
            'gross': event_revs['grossTotal__sum'] or 0,
            'netOfDiscounts': event_revs['total__sum'] or 0,
            'adjustments': event_revs['adjustments__sum'] or 0,
            'fees': event_revs['fees__sum'] or 0,
            'net': event_revs['net__sum'] or 0,
        }

        allocated_venue_expenses = ExpenseItem.objects.filter(
            event__isnull=True,
            expensepurpose__content_type=eventoccurrence_ct,
            expensepurpose__object_id__in=event.eventoccurrence_set.values_list('id', flat=True),
            payTo__location__isnull=False
        )

        total_allocated_venue = sum([
            x.getAllocationForEvents([event,]) * x.total
            for x in allocated_venue_expenses
        ])

        allocated_staff_expenses = ExpenseItem.objects.filter(
            event__isnull=True,
            expensepurpose__content_type=eventstaffmember_ct,
            expensepurpose__object_id__in=event.eventstaffmember_set.values_list('id', flat=True)
        )

        total_allocated_staff = sum([
            x.getAllocationForEvents([event,]) * x.total
            for x in allocated_staff_expenses
        ])

        this_event_statement['expenses'] = {
            'instruction': event.expenseitem_set.filter(
                category=getConstant('financial__classInstructionExpenseCat')
            ).aggregate(Sum('total'))['total__sum'] or 0,
            'direct_venue': event.expenseitem_set.filter(
                category=getConstant('financial__venueRentalExpenseCat')
            ).aggregate(Sum('total'))['total__sum'] or 0,
            'allocated_venue': total_allocated_venue,
            'allocated_staff': total_allocated_staff,
            'direct_other': event.expenseitem_set.exclude(
                category=getConstant('financial__venueRentalExpenseCat')
            ).exclude(
                category=getConstant('financial__classInstructionExpenseCat')
            ).aggregate(Sum('total'))['total__sum'] or 0,
            'fees': event.expenseitem_set.aggregate(Sum('fees'))['fees__sum'] or 0,
        }
        this_event_statement['expenses'].update({
            'venue': sum([
                this_event_statement['expenses']['direct_venue'],
                this_event_statement['expenses']['allocated_venue'],
            ]),
            'other': sum([
                this_event_statement['expenses']['direct_other'],
                this_event_statement['expenses']['allocated_staff'],
            ])
        })

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

    if paginate:
        # Return not just the statement, but also the paginator in the style of
        # ListView's paginate_queryset()
        return (paginator, paged_events, statementByEvent, paged_events.has_other_pages())
    else:
        return statementByEvent


def prepareFinancialDetails(**kwargs):
        context = kwargs.copy()
        timeFilters = {}

        # Determine the period over which the statement should be produced.
        year = kwargs.get('year')
        month = kwargs.get('month')
        day = kwargs.get('day')
        startDate = kwargs.get('startDate')
        endDate = kwargs.get('endDate')
        events = kwargs.get('events')
        occurrences = kwargs.get('occurrences')
        allocationBasis = kwargs.get('allocationBasis')
        basis = kwargs.get('basis')

        context.update({
            'basis': basis,
            'basis_name': EXPENSE_BASES[basis],
            'rangeTitle': '',
        })

        if events:
            timeFilters['event__in'] = events
            if not occurrences:
                context['rangeTitle'] += '; '.join([str(x.name) for x in events])

        if occurrences:
            timeFilters['event__eventoccurrence__in'] = occurrences
            context['rangeTitle'] += '; '.join([
                '{}: {}'.format(x.event.name, x.timeDescription)
                for x in occurrences
            ])

        if startDate:
            timeFilters['%s__gte' % basis] = startDate
            context['rangeType'] = 'Date Range'
            context['rangeTitle'] += str(_('From %s ' % startDate.strftime('%b. %d, %Y')))
        if endDate:
            timeFilters['%s__lt' % basis] = endDate
            context['rangeType'] = 'Date Range'
            context['rangeTitle'] += str(_('To %s ' % endDate.strftime('%b. %d, %Y')))

        if not startDate and not endDate:
            start = None
            delta = None

            if day and month and year:
                start = ensure_localtime(datetime(year, month, day))
                delta = relativedelta(days=1)
                context.update({
                    'rangeType': 'Day',
                    'rangeTitle': start.strftime('%B %d, %Y')
                })
            elif month and year:
                start = ensure_localtime(datetime(year, month, 1))
                delta = relativedelta(months=1)
                context.update({
                    'rangeType': 'Month',
                    'rangeTitle': start.strftime('%B %Y')
                })
            elif events:
                context['rangeType'] = 'Events'
            elif year:
                start = ensure_localtime(datetime(year, 1, 1))
                delta = relativedelta(years=1)
                context.update({
                    'rangeType': 'Year',
                    'rangeTitle': start.strftime('%Y')
                })
            else:
                start = ensure_localtime(datetime(timezone.now().year, 1, 1))
                delta = relativedelta(years=1)
                context.update({
                    'rangeType': 'YTD',
                    'rangeTitle': _('Calendar Year To Date')
                })

            if start and delta:
                timeFilters['%s__gte' % basis] = start
                timeFilters['%s__lt' % basis] = start + delta

        context['startDate'] = timeFilters.get('%s__gte' % basis)
        context['endDate'] = timeFilters.get('%s__lt' % basis)

        # Revenues are booked on receipt basis, not payment/approval basis
        rev_timeFilters = timeFilters.copy()
        rev_basis = basis

        if basis in ['paymentDate', 'approvalDate']:
            rev_basis = 'receivedDate'
            if rev_timeFilters.get('%s__gte' % basis):
                rev_timeFilters['receivedDate__gte'] = rev_timeFilters.get('%s__gte' % basis)
                rev_timeFilters.pop('%s__gte' % basis, None)
            if rev_timeFilters.get('%s__lt' % basis):
                rev_timeFilters['receivedDate__lt'] = rev_timeFilters.get('%s__lt' % basis)
                rev_timeFilters.pop('%s__lt' % basis, None)

        expenseItems = list(
            ExpenseItem.objects.filter(**timeFilters).annotate(
                basisDate=Min(basis)
            ).select_related(
                'category', 'payTo', 'payTo__location', 'event'
            ).prefetch_related(
                'expensepurpose_set', 'expensepurpose_set__content_type',
                'event__eventoccurrence_set'
            ).order_by(basis)
        )
        revenueItems = list(
            RevenueItem.objects.filter(**rev_timeFilters).annotate(
                basisDate=Min(rev_basis)
            ).select_related(
                'category', 'invoiceItem', 'receivedFrom'
            ).prefetch_related(
                'event__eventoccurrence_set'
            ).order_by(rev_basis)
        )

        # select_related('event') returns bare base Event instances, bypassing
        # django-polymorphic dispatch.  Re-fetch using the polymorphic manager so
        # that each item.event is the correct subclass (Series, PublicEvent, etc.)
        # and its __str__ / name reflect the actual event name.
        revenue_event_ids = list({item.event_id for item in revenueItems if item.event_id})
        if revenue_event_ids:
            real_events = {
                e.id: e for e in Event.objects.filter(id__in=revenue_event_ids)
            }
            for item in revenueItems:
                if item.event_id:
                    item.event = real_events.get(item.event_id, item.event)

        context['expenseItems'] = expenseItems
        context['revenueItems'] = revenueItems

        if events:
            # These are needed to allocate non-hourly expenses across events.
            eventoccurrence_ct = ContentType.objects.get_for_model(EventOccurrence).id
            eventstaffmember_ct = ContentType.objects.get_for_model(EventStaffMember).id

            if occurrences:
                purpose_occurrences = occurrences.values_list('id', flat=True)
            else:
                purpose_occurrences = EventOccurrence.objects.filter(
                    event__in=events
                ).values_list('id', flat=True)

            purpose_staff = EventStaffMember.objects.filter(
                event__in=events
            ).values_list('id', flat=True)

            context.update({
                'allocatedVenueExpenseItems': ExpenseItem.objects.filter(
                    event__isnull=True,
                    expensepurpose__content_type=eventoccurrence_ct,
                    expensepurpose__object_id__in=purpose_occurrences,
                    payTo__location__isnull=False
                ).annotate(
                    basisDate=Min(basis)
                ).order_by(basis),
                'allocatedStaffExpenseItems': ExpenseItem.objects.filter(
                event__isnull=True,
                expensepurpose__content_type=eventstaffmember_ct,
                expensepurpose__object_id__in=purpose_staff,
                ).annotate(
                    basisDate=Min(basis)
                ).order_by(basis),
            })
            context.update({
                'allocatedVenueTotal': sum([
                    x.getAllocation(**allocationBasis) * (x.net or 0)
                    for x in context['allocatedVenueExpenseItems']
                ]),
                'allocatedStaffTotal': sum([
                    x.getAllocation(**allocationBasis) * (x.net or 0)
                    for x in context['allocatedStaffExpenseItems']
                ])
            })
            context['allocatedTotal'] = (
                context['allocatedVenueTotal'] + context['allocatedStaffTotal']
            )

        # Registration revenues, instruction and venue expenses
        # are broken out separately.
        instruction_cats = [
            getConstant('financial__classInstructionExpenseCat'),
            getConstant('financial__assistantClassInstructionExpenseCat')
        ]
        venue_cat = getConstant('financial__venueRentalExpenseCat')
        reg_rev_cat = getConstant('financial__registrationsRevenueCat')

        context.update({
            'instructionExpenseItems': sorted(
                [x for x in expenseItems if x.category in instruction_cats],
                key=lambda x: getattr(x.payTo, 'name', '')
            ),
            'venueExpenseItems': sorted(
                [x for x in expenseItems if x.category == venue_cat],
                key=lambda x: getattr(x.payTo, 'name', '')
            ),
            'otherExpenseItems': sorted(
                [
                    x for x in expenseItems if
                    x.category not in (instruction_cats + [venue_cat])
                ],
                key=lambda x: getattr(x.category, 'name', '')
            ),
            'totalExpenses': (
                sum([
                    x.getAllocation(**allocationBasis) * (x.net or 0)
                    for x in expenseItems
                ])
            ),
        })

        context.update({
            'registrationRevenueItems': sorted(
                [x for x in revenueItems if x.category == reg_rev_cat],
                key=lambda x: (
                    getattr(x.event, 'startTime', ensure_timezone(datetime.min)),
                    getattr(x.event, 'uuid', '')
                ),
                reverse=True
            ),
            'otherRevenueItems': sorted(
                [x for x in revenueItems if x.category != reg_rev_cat],
                key=lambda x: getattr(x.category, 'name', '')
            ),
            'totalRevenues': sum([
                x.getAllocation(**allocationBasis) * (x.net or 0) for x in revenueItems
            ]),
        })

        context.update({
            'netProfit': context['totalRevenues'] - context['totalExpenses'],
        })

        return context
