from django.views.generic import DetailView, TemplateView
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, Http404
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from datetime import datetime
import unicodecsv as csv
from calendar import month_name
from urllib.parse import unquote_plus
import re

from braces.views import PermissionRequiredMixin

from danceschool.core.models import StaffMember, Event, EventOccurrence
from danceschool.core.mixins import StaffMemberObjectMixin, FinancialContextMixin
from danceschool.core.utils.timezone import ensure_timezone
from danceschool.core.utils.requests import getIntFromGet, getDateTimeFromGet

from ..models import ExpenseItem, RevenueItem
from ..helpers.reports import (
    prepareFinancialStatement, prepareFinancialDetails,
    prepareStatementByPeriod, prepareStatementByEvent,
)
from ..helpers.csv import getExpenseItemsCSV
from ..constants import EXPENSE_BASES


class StaffMemberPaymentsView(StaffMemberObjectMixin, PermissionRequiredMixin, DetailView):
    model = StaffMember
    template_name = 'financial/staffmember_payments.html'
    permission_required = 'core.view_own_instructor_finances'
    as_csv = False

    def get_context_data(self, **kwargs):
        staff_member = self.object
        context = {}

        query_filter = Q()

        # These will be passed to the template
        year = self.kwargs.get('year')
        eligible_years = list(set([
            x.year for x in ExpenseItem.objects.values_list(
                'accrualDate', flat=True
            ).distinct()
        ]))
        eligible_years.sort(reverse=True)

        if not year or year == 'all':
            int_year = None
            year = 'all'
        else:
            try:
                int_year = int(year)

                # Check for year in kwargs and ensure that it is eligible
                if int_year not in eligible_years:
                    raise Http404(_("Invalid year."))
                query_filter = query_filter & (
                    Q(accrualDate__year=int_year) |
                    Q(paymentDate__year=int_year) |
                    Q(submissionDate__year=int_year)
                )
            except (ValueError, TypeError):
                raise Http404(_("Invalid year."))

        # No point in continuing if we can't actually match this staff member to their payments.
        if not hasattr(staff_member, 'userAccount'):
            return super(DetailView, self).get_context_data(staff_member=staff_member)

        all_payments = getattr(
            getattr(staff_member, 'transactionparty'),
            'expenseitem_set',
            ExpenseItem.objects.none()
        ).filter(query_filter).order_by('-submissionDate')

        paid_items = all_payments.filter(
            paid=True, reimbursement=False
        ).order_by('-paymentDate')
        unpaid_items = all_payments.filter(paid=False).order_by('-submissionDate')
        reimbursement_items = all_payments.filter(
            paid=True, reimbursement=True
        ).order_by('-paymentDate')

        if int_year:
            time_lb = ensure_timezone(datetime(int_year, 1, 1, 0, 0))
            time_ub = ensure_timezone(datetime(int_year + 1, 1, 1, 0, 0))
        else:
            time_lb = ensure_timezone(datetime(timezone.now().year, 1, 1, 0, 0))
            time_ub = ensure_timezone(datetime(timezone.now().year + 1, 1, 1, 0, 0))

        paid_this_year = paid_items.filter(
            paymentDate__gte=time_lb, paymentDate__lt=time_ub
        ).order_by('-paymentDate')
        accrued_paid_this_year = paid_items.filter(
            accrualDate__gte=time_lb, accrualDate__lt=time_ub
        ).order_by('-paymentDate')
        reimbursements_this_year = all_payments.filter(
            paymentDate__gte=time_lb, paymentDate__lt=time_ub,
            paid=True, reimbursement=True
        )

        context.update({
            'instructor': staff_member,  # DEPRECATED
            'staff_member': staff_member,
            'current_year': year,
            'eligible_years': eligible_years,
            'all_payments': all_payments,
            'paid_items': paid_items,
            'unpaid_items': unpaid_items,
            'reimbursement_items': reimbursement_items,
            'paid_this_year': paid_this_year,
            'accrued_paid_this_year': accrued_paid_this_year,
            'reimbursements_this_year': reimbursements_this_year,
            'total_paid_alltime': sum(filter(None, [x.total for x in paid_items])),
            'total_awaiting_payment': sum(filter(None, [x.total for x in unpaid_items])),
            'total_paid_this_year': sum(filter(None, [x.total for x in paid_this_year])),
            'total_reimbursements': sum(filter(None, [x.total for x in reimbursements_this_year])),
        })

        # Note: This get the detailview's context, not all the mixins.  Supering itself led to an infinite loop.
        return super(DetailView, self).get_context_data(**context)

    def dispatch(self, request, *args, **kwargs):
        if 'as_csv' in kwargs:
            self.as_csv = True
        return super().dispatch(request, *args, **kwargs)

    def render_to_response(self, context, **response_kwargs):
        if self.as_csv:
            return self.render_to_csv(context)
        return super().render_to_response(context, **response_kwargs)

    def render_to_csv(self, context):
        staff_member = context['staff_member']
        if hasattr(getattr(staff_member, 'transactionparty', None), 'expenseitem_set'):
            all_expenses = context['all_payments']
        else:
            all_expenses = ExpenseItem.objects.none()
        return getExpenseItemsCSV(all_expenses, scope='instructor')


class OtherStaffMemberPaymentsView(StaffMemberPaymentsView):
    permission_required = 'core.view_other_instructor_finances'

    def get_object(self, queryset=None):
        if 'first_name' in self.kwargs and 'last_name' in self.kwargs:
            first_name = re.sub('^_$', '', self.kwargs['first_name'])
            last_name = re.sub('^_$', '', self.kwargs['last_name'])

            return get_object_or_404(
                StaffMember.objects.filter(
                    firstName=unquote_plus(first_name).replace('_', ' '),
                    lastName=unquote_plus(last_name).replace('_', ' ')
                )
            )
        else:
            return None


class FinancesByEventView(PermissionRequiredMixin, TemplateView):
    permission_required = 'financial.view_finances_byevent'
    cache_timeout = 3600
    template_name = 'financial/finances_byevent.html'
    as_csv = False
    paginate_by = 25

    def get_paginate_by(self, queryset=None):
        if self.as_csv:
            return 1000
        else:
            return self.paginate_by

    def get_context_data(self, **kwargs):
        context = {}

        # These will be passed to the template
        year = self.kwargs.get('year')
        eligible_years = list(set(
            [
                x.year for x in
                ExpenseItem.objects.values_list('accrualDate', flat=True).distinct()
            ]
        ))
        eligible_years.sort(reverse=True)

        if not year or year == 'all':
            int_year = None
            year = 'all'
        else:
            try:
                int_year = int(year)

                # Check for year in kwargs and ensure that it is eligible
                if int_year not in eligible_years:
                    raise Http404(_("Invalid year."))
            except (ValueError, TypeError):
                raise Http404(_("Invalid year."))

        context['current_year'] = year
        context['eligible_years'] = eligible_years

        page = self.kwargs.get('page') or self.request.GET.get('page') or 1

        context['statement'] = prepareFinancialStatement(year=int_year)
        paginator, page_obj, statementByEvent, is_paginated = prepareStatementByEvent(
            year=int_year, page=page, paginate_by=self.get_paginate_by()
        )
        context.update({
            'paginator': paginator,
            'page_obj': page_obj,
            'is_paginated': is_paginated,
        })
        context['statement']['statementByEvent'] = statementByEvent

        # Get a list of all roles with positive registrations in the statement:
        role_set = set()
        for x in statementByEvent:
            role_set.update(list(x.get('registrations').keys()))
        role_list = list(role_set)
        sorted(role_list, key=lambda x: (x is None, x))
        context['roles'] = role_list

        return super().get_context_data(**context)

    def dispatch(self, request, *args, **kwargs):
        if 'as_csv' in kwargs:
            self.as_csv = True
        return super().dispatch(request, *args, **kwargs)

    def render_to_response(self, context, **response_kwargs):
        if self.as_csv:
            return self.render_to_csv(context)
        return super().render_to_response(context, **response_kwargs)

    def render_to_csv(self, context):
        statement = context['statement']
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="financialStatementByEvent.csv"'

        roles = set()
        for y in statement['statementByEvent']:
            roles.update(list(y.get('registrations', {}).keys()))

        writer = csv.writer(response, csv.excel)
        response.write(u'\ufeff'.encode('utf8'))  # BOM (optional...Excel needs it to open UTF-8 file properly)

        header_list = [
            _('Event'),
            _('Month'),
        ]
        for role in roles:
            header_list.append(
                _('Registrations: {role}'.format(role=str(role or _('Unspecified')).title()))
            )
        header_list += [
            _('Revenues: Gross'),
            _('Revenues: Net'),
            _('Expenses: Instruction'),
            _('Expenses: Venue'),
            _('Expenses: Other'),
            _('Expenses: Total'),
            _('Net Profit'),
        ]
        writer.writerow(header_list)

        for x in statement['statementByEvent']:
            this_row_data = [
                x['event_name'],
                x['month_name'],
            ]
            for role in roles:
                this_row_data.append(x.get('registrations', {}).get(role, 0))
            this_row_data += [
                x['revenues']['gross'],
                x['revenues']['net'],
                x['expenses']['instruction'],
                x['expenses']['venue'],
                x['expenses']['other'],
                x['expenses']['total'],
                x['net_profit'],
            ]
            writer.writerow(this_row_data)

        return response


class FinancesByPeriodView(PermissionRequiredMixin, TemplateView):
    permission_required = 'financial.view_finances_bymonth'
    cache_timeout = 3600
    template_name = 'financial/finances_byperiod.html'
    as_csv = False
    paginate_by = 24
    period_type = None
    base_view = None
    base_view_csv = None

    def get_paginate_by(self, queryset=None):
        if self.as_csv:
            return 1000
        else:
            return self.paginate_by

    def get(self, request, *args, **kwargs):
        '''
        Allow passing of basis and time limitations
        '''
        try:
            year = int(self.kwargs.get('year'))
        except (ValueError, TypeError):
            year = getIntFromGet(request, 'year')

        kwargs.update({
            'year': year,
            'basis': request.GET.get('basis'),
        })

        if kwargs.get('basis') not in EXPENSE_BASES.keys():
            kwargs['basis'] = 'accrualDate'

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = {}

        # Determine the period over which the statement should be produced.
        year = kwargs.get('year')

        eligible_years = list(set(
            [x.year for x in ExpenseItem.objects.values_list('accrualDate', flat=True).distinct()]
        ))
        eligible_years.sort(reverse=True)

        if year and year not in eligible_years:
            raise Http404(_("Invalid year."))

        context.update({
            'basis': kwargs.get('basis'),
            'basis_name': EXPENSE_BASES[kwargs.get('basis')],
            'year': year,
            'current_year': year or 'all',
            'eligible_years': eligible_years,
            'period_type': self.period_type,
            'base_view': self.base_view,
            'base_view_csv': self.base_view_csv,
        })

        page = self.kwargs.get('page') or self.request.GET.get('page') or 1

        context['statement'] = prepareFinancialStatement(year=year)
        paginator, page_obj, statementByPeriod, is_paginated = prepareStatementByPeriod(
            year=year, basis=context['basis'], type=self.period_type,
            page=page, paginate_by=self.get_paginate_by()
        )
        context.update({
            'paginator': paginator,
            'page_obj': page_obj,
            'is_paginated': is_paginated,
        })
        context['statement']['statementByPeriod'] = statementByPeriod

        return super().get_context_data(**context)

    def dispatch(self, request, *args, **kwargs):
        if 'as_csv' in kwargs:
            self.as_csv = True
        return super().dispatch(request, *args, **kwargs)

    def render_to_response(self, context, **response_kwargs):
        if self.as_csv:
            return self.render_to_csv(context)
        return super().render_to_response(context, **response_kwargs)

    def render_to_csv(self, context):
        statement = context['statement']
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = \
            'attachment; filename="financialStatementBy{}.csv"'.format(
                str(self.period_type).title()
            )

        writer = csv.writer(response, csv.excel)
        response.write(u'\ufeff'.encode('utf8'))  # BOM (optional...Excel needs it to open UTF-8 file properly)

        header_list = [
            _('Month Name'),
            _('Revenues: Net'),
            _('Expenses: Instruction'),
            _('Expenses: Venue'),
            _('Expenses: Other'),
            _('Expenses: Total'),
            _('Registrations'),
            _('Net Profit'),
        ]
        writer.writerow(header_list)

        for x in statement['statementByPeriod']:
            this_row_data = [
                x['period_name'],
                x['revenues'],
                x['expenses']['instruction'],
                x['expenses']['venue'],
                x['expenses']['other'],
                x['expenses']['total'],
                x['registrations'],
                x['net_profit'],
            ]
            writer.writerow(this_row_data)

        return response


class FinancesByMonthView(FinancesByPeriodView):
    period_type = 'month'
    base_view = 'financesByMonth'
    base_view_csv = 'financesByMonthCSV'


class FinancesByDateView(FinancesByPeriodView):
    period_type = 'date'
    base_view = 'financesByDate'
    base_view_csv = 'financesByDateCSV'


class FinancialDetailView(FinancialContextMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'financial.view_finances_detail'
    template_name = 'financial/finances_detail.html'

    def get(self, request, *args, **kwargs):
        '''
        Pass any permissable GET data.  URL parameters override GET parameters
        '''
        try:
            year = int(self.kwargs.get('year'))
        except (ValueError, TypeError):
            year = getIntFromGet(request, 'year')

        if self.kwargs.get('month'):
            try:
                month = int(self.kwargs.get('month'))
            except (ValueError, TypeError):
                try:
                    month = list(month_name).index(self.kwargs.get('month').title())
                except (ValueError, TypeError):
                    month = None
        else:
            month = getIntFromGet(request, 'month')

        try:
            day = int(self.kwargs.get('day'))
        except (ValueError, TypeError):
            day = getIntFromGet(request, 'day')

        try:
            event_ids = [int(self.kwargs.get('event')),]
        except (ValueError, TypeError):
            event_ids = getIntFromGet(request, 'events', force_list=True)

        events = None
        if event_ids:
            events = Event.objects.prefetch_related(
                'eventoccurrence_set'
            ).filter(id__in=event_ids)

        try:
            occurrence_ids = [int(self.kwargs.get('occurrence')),]
        except (ValueError, TypeError):
            occurrence_ids = getIntFromGet(request, 'occurrences', force_list=True)

        occurrences = None
        if events and occurrence_ids:
            occurrences = EventOccurrence.objects.filter(
                event__in=events, id__in=occurrence_ids
            ).select_related('event')

        # Prevents producing an event-level summary when invalid occurrences
        # are passed.
        if occurrence_ids and not occurrences:
            events = None

        kwargs.update({
            'year': year,
            'month': month,
            'day': day,
            'startDate': getDateTimeFromGet(request, 'startDate'),
            'endDate': getDateTimeFromGet(request, 'endDate'),
            'basis': request.GET.get('basis'),
            'events': events,
            'occurrences': occurrences,
            'allocationBasis': {},
        })

        # The allocation basis determines whether expenses are reported in full
        # or only fractionally.
        if (event_ids and events) and (occurrence_ids and occurrences):
            kwargs['allocationBasis']['occurrences'] = occurrences
        if (event_ids and events):
            kwargs['allocationBasis']['events'] = events

        if kwargs.get('basis') not in EXPENSE_BASES.keys():
            kwargs['basis'] = 'accrualDate'

        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        return prepareFinancialDetails(**kwargs)
