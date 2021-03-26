from django.views.generic import DetailView, TemplateView, CreateView, View, FormView
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, Http404, HttpResponseBadRequest, HttpResponseRedirect
from django.db.models import Q, Sum, F, Min
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.utils.translation import gettext_lazy as _, gettext
from django.utils import timezone
from django.contrib.messages.views import SuccessMessageMixin
from django.forms.models import model_to_dict

from datetime import datetime
from dateutil.relativedelta import relativedelta
import unicodecsv as csv
from calendar import month_name
from urllib.parse import unquote_plus
from braces.views import PermissionRequiredMixin, StaffuserRequiredMixin, UserFormKwargsMixin
from collections import OrderedDict
from itertools import chain
import re

from danceschool.core.models import Instructor, Location, Event, StaffMember, EventStaffCategory
from danceschool.core.constants import getConstant
from danceschool.core.mixins import StaffMemberObjectMixin, FinancialContextMixin, AdminSuccessURLMixin
from danceschool.core.utils.timezone import ensure_timezone, ensure_localtime
from danceschool.core.utils.requests import getIntFromGet, getDateTimeFromGet

from .models import ExpenseItem, RevenueItem, ExpenseCategory, RevenueCategory, RepeatedExpenseRule, StaffMemberWageInfo
from .helpers import (
    prepareFinancialStatement, getExpenseItemsCSV, getRevenueItemsCSV, prepareStatementByPeriod,
    prepareStatementByEvent, createExpenseItemsForEvents, createExpenseItemsForVenueRental, createGenericExpenseItems,
    createRevenueItemsForRegistrations
)
from .forms import (
    ExpenseReportingForm, RevenueReportingForm, CompensationRuleUpdateForm,
    CompensationRuleResetForm, ExpenseRuleGenerationForm
)
from .constants import EXPENSE_BASES


class ExpenseReportingView(
    AdminSuccessURLMixin, StaffuserRequiredMixin, UserFormKwargsMixin,
    SuccessMessageMixin, CreateView
):
    template_name = 'cms/forms/display_crispy_form_classbased_admin.html'
    form_class = ExpenseReportingForm
    success_message = _('Expense item successfully submitted.')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'form_title': _('Report Expenses'),
            'form_description': _('Use this form to report expenses.'),
        })
        return context


class RevenueReportingView(
    AdminSuccessURLMixin, StaffuserRequiredMixin, UserFormKwargsMixin,
    SuccessMessageMixin, CreateView
):
    template_name = 'cms/forms/display_crispy_form_classbased_admin.html'
    form_class = RevenueReportingForm
    success_message = _('Revenue item successfully submitted.')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'form_title': _('Report Revenues'),
            'form_description': _('Use this form to report revenues.'),
        })
        return context


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
            event_id = int(self.kwargs.get('event'))
        except (ValueError, TypeError):
            event_id = getIntFromGet(request, 'event')

        event = None
        if event_id:
            try:
                event = Event.objects.get(id=event_id)
            except ObjectDoesNotExist:
                pass

        kwargs.update({
            'year': year,
            'month': month,
            'day': day,
            'startDate': getDateTimeFromGet(request, 'startDate'),
            'endDate': getDateTimeFromGet(request, 'endDate'),
            'basis': request.GET.get('basis'),
            'event': event,
        })

        if kwargs.get('basis') not in EXPENSE_BASES.keys():
            kwargs['basis'] = 'accrualDate'

        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = kwargs.copy()
        timeFilters = {}

        # Determine the period over which the statement should be produced.
        year = kwargs.get('year')
        month = kwargs.get('month')
        day = kwargs.get('day')
        startDate = kwargs.get('startDate')
        endDate = kwargs.get('endDate')
        event = kwargs.get('event')

        basis = kwargs.get('basis')

        context.update({
            'basis': basis,
            'basis_name': EXPENSE_BASES[basis],
            'rangeTitle': '',
        })

        if event:
            timeFilters['event'] = event
            context['rangeTitle'] += '%s ' % event.name

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
            elif event:
                context['rangeType'] = 'Event'
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

        expenseItems = ExpenseItem.objects.filter(**timeFilters).annotate(
            net=F('total') + F('adjustments') + F('fees'),
            basisDate=Min(basis)
        ).order_by(basis)
        revenueItems = RevenueItem.objects.filter(**rev_timeFilters).annotate(
            net=F('total') + F('adjustments') - F('fees'),
            basisDate=Min(rev_basis)
        ).order_by(rev_basis)

        context['expenseItems'] = expenseItems
        context['revenueItems'] = revenueItems

        # Registration revenues, instruction and venue expenses
        # are broken out separately.

        context.update({
            'instructionExpenseItems': expenseItems.filter(
                category__in=[
                    getConstant('financial__classInstructionExpenseCat'),
                    getConstant('financial__assistantClassInstructionExpenseCat')
                ]
            ).order_by('payTo__name'),
            'venueExpenseItems': expenseItems.filter(
                category=getConstant('financial__venueRentalExpenseCat')
            ).order_by('payTo__name'),
            'otherExpenseItems': expenseItems.exclude(
                category__in=[
                    getConstant('financial__classInstructionExpenseCat'),
                    getConstant('financial__assistantClassInstructionExpenseCat'),
                    getConstant('financial__venueRentalExpenseCat')
                ]
            ).order_by('category'),
            'expenseCategoryTotals': ExpenseCategory.objects.filter(
                expenseitem__in=expenseItems
            ).annotate(
                category_total=Sum('expenseitem__total'),
                category_adjustments=Sum('expenseitem__adjustments'),
                category_fees=Sum('expenseitem__fees')
            ).annotate(
                category_net=F('category_total') + F('category_adjustments') + F('category_fees')
            ),
        })
        context.update({
            'instructionExpenseInstructorTotals': StaffMember.objects.filter(
                transactionparty__expenseitem__in=context['instructionExpenseItems']
            ).annotate(
                instructor_total=Sum('transactionparty__expenseitem__total'),
                instructor_adjustments=Sum('transactionparty__expenseitem__adjustments'),
                instructor_fees=Sum('transactionparty__expenseitem__fees')
            ).annotate(
                instructor_net=F('instructor_total') + F('instructor_adjustments') + F('instructor_fees')
            ),
            'instructionExpenseOtherTotal': context['instructionExpenseItems'].filter(
                payTo__staffMember__isnull=True
            ).annotate(
                net=F('total') + F('adjustments') + F('fees')
            ).aggregate(
                instructor_total=Sum('total'),
                instructor_adjustments=Sum('adjustments'),
                instructor_fees=Sum('fees'),
                instructor_net=Sum('net')
            ),

            'venueExpenseVenueTotals': Location.objects.filter(
                transactionparty__expenseitem__in=context['venueExpenseItems']
            ).annotate(
                location_total=Sum('transactionparty__expenseitem__total'),
                location_adjustments=Sum('transactionparty__expenseitem__adjustments'),
                location_fees=Sum('transactionparty__expenseitem__fees')
            ).annotate(
                location_net=F('location_total') + F('location_adjustments') + F('location_fees')
            ),
            'venueExpenseOtherTotal': context['venueExpenseItems'].filter(
                payTo__location__isnull=True
            ).annotate(
                location_net=F('total') + F('adjustments') + F('fees')
            ).aggregate(
                location_total=Sum('total'),
                location_adjustments=Sum('adjustments'),
                location_fees=Sum('fees'), location_net=Sum('net')
            ),

            'totalInstructionExpenses': sum([
                x.category_net or 0 for x in
                context['expenseCategoryTotals'].filter(
                    id__in=[
                        getConstant('financial__classInstructionExpenseCat').id,
                        getConstant('financial__assistantClassInstructionExpenseCat').id
                    ]
                )
            ]),
            'totalVenueExpenses': sum([
                x.category_net or 0 for x in
                context['expenseCategoryTotals'].filter(
                    id=getConstant('financial__venueRentalExpenseCat').id
                )
            ]),
            'totalOtherExpenses': sum([
                x.category_net or 0 for x in
                context['expenseCategoryTotals'].exclude(
                    id__in=[
                        getConstant('financial__classInstructionExpenseCat').id,
                        getConstant('financial__assistantClassInstructionExpenseCat').id,
                        getConstant('financial__venueRentalExpenseCat').id
                    ]
                )
            ]),

            'totalExpenses': sum([x.category_net or 0 for x in context['expenseCategoryTotals']]),
        })

        context.update({
            'registrationRevenueItems': revenueItems.filter(
                category=getConstant('financial__registrationsRevenueCat')
            ).order_by('-event__startTime', 'event__uuid'),
            'otherRevenueItems': revenueItems.exclude(
                category=getConstant('financial__registrationsRevenueCat')
            ).order_by('category'),
            'revenueCategoryTotals': RevenueCategory.objects.filter(
                revenueitem__in=revenueItems
            ).annotate(
                category_total=Sum('revenueitem__total'),
                category_adjustments=Sum('revenueitem__adjustments'),
                category_fees=Sum('revenueitem__fees')
            ).annotate(
                category_net=F('category_total') + F('category_adjustments') - F('category_fees')
            ),
        })
        context.update({
            'registrationRevenueEventTotals': Event.objects.filter(
                revenueitem__in=context['registrationRevenueItems']
            ).annotate(
                event_total=Sum('revenueitem__total'),
                event_adjustments=Sum('revenueitem__adjustments'),
                event_fees=Sum('revenueitem__fees')
            ).annotate(
                event_net=F('event_total') + F('event_adjustments') - F('event_fees')
            ),
            'registrationRevenueOtherTotal': context['registrationRevenueItems'].filter(
                event__isnull=True
            ).annotate(
                event_net=F('total') + F('adjustments') - F('fees')
            ).aggregate(
                event_total=Sum('total'),
                event_adjustments=Sum('adjustments'),
                event_fees=Sum('fees'),
                event_net=Sum('net')
            ),

            'totalRegistrationRevenues': sum([
                x.category_net or 0 for x in
                context['revenueCategoryTotals'].filter(
                    id=getConstant('financial__registrationsRevenueCat').id
                )
            ]),
            'totalOtherRevenues': sum([
                x.category_net or 0 for x in
                context['revenueCategoryTotals'].exclude(
                    id=getConstant('financial__registrationsRevenueCat').id
                )
            ]),
            'totalRevenues': sum([x.category_net or 0 for x in context['revenueCategoryTotals']]),
        })

        context.update({
            'netProfit': context['totalRevenues'] - context['totalExpenses'],
        })

        return super().get_context_data(**context)


class CompensationActionView(
    SuccessMessageMixin, AdminSuccessURLMixin, PermissionRequiredMixin,
    FinancialContextMixin, FormView
):
    '''
    Base class with repeated logic for update and replace actions.
    '''
    permission_required = 'core.change_staffmember'

    def dispatch(self, request, *args, **kwargs):
        ids = request.GET.get('ids')
        ct = getIntFromGet(request, 'ct')

        try:
            contentType = ContentType.objects.get(id=ct)
            self.objectClass = contentType.model_class()
        except (ValueError, ObjectDoesNotExist):
            return HttpResponseBadRequest(_('Invalid content type passed.'))

        # This view only deals with StaffMember
        if not isinstance(self.objectClass(), StaffMember):
            return HttpResponseBadRequest(_('Invalid content type passed.'))

        try:
            self.queryset = self.objectClass.objects.filter(id__in=[int(x) for x in ids.split(', ')])
        except ValueError:
            return HttpResponseBadRequest(_('Invalid ids passed'))

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self, **kwargs):
        ''' pass the list of staff members along to the form '''
        kwargs = super().get_form_kwargs(**kwargs)
        kwargs['staffmembers'] = self.queryset
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'staffmembers': self.queryset,
            'rateRuleValues': dict(RepeatedExpenseRule.RateRuleChoices.choices),
        })

        return context


class CompensationRuleUpdateView(CompensationActionView):
    '''
    This view is for an admin action to bulk update staff member compensation information.
    '''
    template_name = 'financial/update_staff_compensation_rules.html'
    form_class = CompensationRuleUpdateForm
    success_message = _('Staff member compensation rules updated successfully.')

    def form_valid(self, form):
        category = form.cleaned_data.pop('category', None)

        for staffmember in self.queryset:
            staffmember.expenserules.update_or_create(
                category=category,
                defaults=form.cleaned_data,
            )

        return super().form_valid(form)


class CompensationRuleResetView(CompensationActionView):
    '''
    This view is for an admin action to bulk delete custom staff member compensation information
    and/or reset to category defaults.
    '''
    template_name = 'financial/reset_staff_compensation_rules.html'
    form_class = CompensationRuleResetForm
    success_message = _('Staff member compensation rules reset successfully.')

    def form_valid(self, form):
        resetHow = form.cleaned_data.get('resetHow')

        cat_numbers = [
            int(x.split('_')[1]) for x in [
                y[0] for y in form.cleaned_data.items() if y[1] and 'category_' in y[0]
            ]
        ]

        if resetHow == 'DELETE':
            StaffMemberWageInfo.objects.filter(staffMember__in=self.queryset, category__in=cat_numbers).delete()
        elif resetHow == 'COPY':
            cats = EventStaffCategory.objects.filter(id__in=cat_numbers, defaultwage__isnull=False)
            for this_cat in cats:
                this_default = model_to_dict(
                    this_cat.defaultwage,
                    exclude=('category', 'id', 'repeatedexpenserule_ptr', 'lastRun')
                )

                for staffmember in self.queryset:
                    staffmember.expenserules.update_or_create(
                        category=this_cat,
                        defaults=this_default,
                    )

        return super().form_valid(form)


class ExpenseRuleGenerationView(AdminSuccessURLMixin, PermissionRequiredMixin, FormView):
    template_name = 'financial/expense_generation.html'
    form_class = ExpenseRuleGenerationForm
    permission_required = 'financial.can_generate_repeated_expenses'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        fields = getattr(context.get('form', {}), 'fields', OrderedDict())

        context.update({
            'form_title': _('Generate rule-based financial items'),
            'form_description': _(
                'This form is used to generate expense items and revenue items ' +
                'based on pre-set repeated expense rules. Please check the boxes ' +
                'for the rules that you wish to apply. Depending on your site ' +
                'settings, regular automatic generation of these financial items ' +
                'may already be occurring. Using this form should not lead duplicate ' +
                'items to be generated under these rules.'
            ),
            'staff_keys': [
                key for key in fields.keys()
                if key.startswith('staff') and key != 'staff'
            ],
            'venue_keys': [
                key for key in fields.keys()
                if key.startswith('location') or key.startswith('room')
            ],
            'generic_keys': [
                key for key in fields.keys()
                if key.startswith('generic') and key != 'generic'
            ],
        })
        return context

    def form_valid(self, form):
        try:
            generic_rules = RepeatedExpenseRule.objects.filter(id__in=[
                int(key.split('_')[-1]) for key, value in form.cleaned_data.items() if key.startswith('rule_') and value
            ]).order_by('id')
            location_rules = RepeatedExpenseRule.objects.filter(id__in=[
                int(key.split('_')[-1]) for key, value in form.cleaned_data.items() if (
                    key.startswith('locationrule_') or key.startswith('roomrule_')
                ) and value
            ]).order_by('id')
            staff_rules = RepeatedExpenseRule.objects.filter(id__in=[
                int(key.split('_')[-1]) for key, value in form.cleaned_data.items() if (
                    key.startswith('staffdefaultrule_') or key.startswith('staffmemberrule_')
                ) and value
            ]).order_by('id')
        except ValueError:
            return HttpResponseBadRequest(_('Invalid rules provided.'))

        response_items = [
            {
                'name': x.ruleName,
                'id': x.id,
                'type': _('Venue rental'),
                'created': createExpenseItemsForVenueRental(rule=x)
            } for x in location_rules
        ]
        response_items += [
            {
                'name': x.ruleName,
                'id': x.id,
                'type': _('Staff expenses'),
                'created': createExpenseItemsForEvents(rule=x)
            } for x in staff_rules
        ]
        response_items += [
            {
                'name': x.ruleName,
                'id': x.id,
                'type': _('Other expenses'),
                'created': createGenericExpenseItems(rule=x)
            } for x in generic_rules
        ]
        if form.cleaned_data.get('registrations'):
            response_items += [{
                'name': _('Revenue items for registrations'),
                'type': _('Revenue items for registrations'),
                'created': createRevenueItemsForRegistrations()
            }, ]

        success_message = gettext(
            'Successfully created {count} financial items.'.format(
                count=sum([x.get('created', 0) or 0 for x in response_items])
            )
        )
        messages.success(self.request, success_message)
        return HttpResponseRedirect(self.get_success_url())


class AllExpensesViewCSV(PermissionRequiredMixin, View):
    permission_required = 'financial.export_financial_data'

    def dispatch(self, request, *args, **kwargs):
        all_expenses = ExpenseItem.objects.order_by('-paid', '-approved', '-submissionDate')
        return getExpenseItemsCSV(all_expenses, scope='all')


class AllRevenuesViewCSV(PermissionRequiredMixin, View):
    permission_required = 'financial.export_financial_data'

    def dispatch(self, request, *args, **kwargs):
        all_revenues = RevenueItem.objects.order_by('-submissionDate')
        return getRevenueItemsCSV(all_revenues)
