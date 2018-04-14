from django.views.generic import DetailView, TemplateView, CreateView, View, FormView
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, Http404, HttpResponseBadRequest
from django.db.models import Q, Sum, F, Min
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone
from django.contrib.messages.views import SuccessMessageMixin

from datetime import datetime
import unicodecsv as csv
from calendar import month_name
from urllib.parse import unquote_plus
from braces.views import PermissionRequiredMixin, StaffuserRequiredMixin, UserFormKwargsMixin

from danceschool.core.models import Instructor, Location, Event, StaffMember
from danceschool.core.constants import getConstant
from danceschool.core.mixins import StaffMemberObjectMixin, FinancialContextMixin, AdminSuccessURLMixin
from danceschool.core.utils.timezone import ensure_timezone
from danceschool.core.utils.requests import getIntFromGet, getDateTimeFromGet

from .models import ExpenseItem, RevenueItem, ExpenseCategory, RevenueCategory, RepeatedExpenseRule
from .helpers import prepareFinancialStatement, getExpenseItemsCSV, getRevenueItemsCSV, prepareStatementByMonth, prepareStatementByEvent
from .forms import ExpenseReportingForm, RevenueReportingForm, CompensationRuleUpdateForm
from .constants import EXPENSE_BASES


class ExpenseReportingView(AdminSuccessURLMixin, StaffuserRequiredMixin, UserFormKwargsMixin, SuccessMessageMixin, CreateView):
    template_name = 'cms/forms/display_crispy_form_classbased_admin.html'
    form_class = ExpenseReportingForm
    success_message = _('Expense item successfully submitted.')

    def get_context_data(self,**kwargs):
        context = super(ExpenseReportingView,self).get_context_data(**kwargs)

        context.update({
            'form_title': _('Report Expenses'),
            'form_description': _('Use this form to report expenses.'),
        })
        return context


class RevenueReportingView(AdminSuccessURLMixin, StaffuserRequiredMixin, UserFormKwargsMixin, SuccessMessageMixin, CreateView):
    template_name = 'cms/forms/display_crispy_form_classbased_admin.html'
    form_class = RevenueReportingForm
    success_message = _('Revenue item successfully submitted.')

    def get_context_data(self,**kwargs):
        context = super(RevenueReportingView,self).get_context_data(**kwargs)

        context.update({
            'form_title': _('Report Revenues'),
            'form_description': _('Use this form to report revenues.'),
        })
        return context


class InstructorPaymentsView(StaffMemberObjectMixin, PermissionRequiredMixin, DetailView):
    model = Instructor
    template_name = 'financial/instructor_payments.html'
    permission_required = 'core.view_own_instructor_finances'
    as_csv = False

    def get_context_data(self,**kwargs):
        instructor = self.object
        context = {}

        query_filter = Q()

        # These will be passed to the template
        year = self.kwargs.get('year')
        eligible_years = list(set([x.year for x in ExpenseItem.objects.values_list('accrualDate',flat=True).distinct()]))
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
                query_filter = query_filter & (Q(accrualDate__year=int_year) | Q(paymentDate__year=int_year) | Q(submissionDate__year=int_year))
            except (ValueError, TypeError):
                raise Http404(_("Invalid year."))

        # No point in continuing if we can't actually match this instructor to their payments.
        if not hasattr(instructor,'userAccount'):
            return super(DetailView, self).get_context_data(instructor=instructor)

        all_payments = instructor.userAccount.payToUser.filter(query_filter).order_by('-submissionDate')

        paid_items = all_payments.filter(**{'paid':True,'reimbursement':False}).order_by('-paymentDate')
        unpaid_items = all_payments.filter(**{'paid':False}).order_by('-submissionDate')
        reimbursement_items = all_payments.filter(**{'paid':True,'reimbursement':True}).order_by('-paymentDate')

        if int_year:
            time_lb = ensure_timezone(datetime(int_year,1,1,0,0))
            time_ub = ensure_timezone(datetime(int_year + 1,1,1,0,0))
        else:
            time_lb = ensure_timezone(datetime(timezone.now().year,1,1,0,0))
            time_ub = ensure_timezone(datetime(timezone.now().year + 1,1,1,0,0))

        paid_this_year = paid_items.filter(paymentDate__gte=time_lb,paymentDate__lt=time_ub).order_by('-paymentDate')
        accrued_paid_this_year = paid_items.filter(accrualDate__gte=time_lb,accrualDate__lt=time_ub).order_by('-paymentDate')
        reimbursements_this_year = all_payments.filter(paymentDate__gte=time_lb,paymentDate__lt=time_ub,paid=True,reimbursement=True)

        context.update({
            'instructor': instructor,
            'current_year': year,
            'eligible_years': eligible_years,
            'all_payments': all_payments,
            'paid_items': paid_items,
            'unpaid_items': unpaid_items,
            'reimbursement_items': reimbursement_items,
            'paid_this_year': paid_this_year,
            'accrued_paid_this_year': accrued_paid_this_year,
            'reimbursements_this_year': reimbursements_this_year,
            'total_paid_alltime': sum(filter(None,[x.total for x in paid_items])),
            'total_awaiting_payment': sum(filter(None,[x.total for x in unpaid_items])),
            'total_paid_this_year': sum(filter(None,[x.total for x in paid_this_year])),
            'total_reimbursements': sum(filter(None,[x.total for x in reimbursements_this_year])),
        })

        # Note: This get the detailview's context, not all the mixins.  Supering itself led to an infinite loop.
        return super(DetailView, self).get_context_data(**context)

    def dispatch(self, request, *args, **kwargs):
        if 'as_csv' in kwargs:
            self.as_csv = True
        return super(InstructorPaymentsView, self).dispatch(request, *args, **kwargs)

    def render_to_response(self, context, **response_kwargs):
        if self.as_csv:
            return self.render_to_csv(context)
        return super(InstructorPaymentsView, self).render_to_response(context, **response_kwargs)

    def render_to_csv(self, context):
        instructor = context['instructor']
        if hasattr(instructor.userAccount,'payToUser'):
            all_expenses = context['all_payments']
        else:
            all_expenses = ExpenseItem.objects.none()
        return getExpenseItemsCSV(all_expenses,scope='instructor')


class OtherInstructorPaymentsView(InstructorPaymentsView):
    permission_required = 'core.view_other_instructor_finances'

    def get_object(self, queryset=None):
        if 'first_name' in self.kwargs and 'last_name' in self.kwargs:
            return get_object_or_404(
                Instructor.objects.filter(**{'firstName': unquote_plus(self.kwargs['first_name']).replace('_',' '), 'lastName': unquote_plus(self.kwargs['last_name']).replace('_',' ')})
            )
        else:
            return None


class FinancesByEventView(PermissionRequiredMixin, TemplateView):
    permission_required = 'financial.view_finances_byevent'
    cache_timeout = 3600
    template_name = 'financial/finances_byevent.html'
    as_csv = False
    paginate_by = 25

    def get_paginate_by(self,queryset=None):
        if self.as_csv:
            return 1000
        else:
            return self.paginate_by

    def get_context_data(self,**kwargs):
        context = {}

        # These will be passed to the template
        year = self.kwargs.get('year')
        eligible_years = list(set([x.year for x in ExpenseItem.objects.values_list('accrualDate',flat=True).distinct()]))
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
        paginator, page_obj, statementByEvent, is_paginated = prepareStatementByEvent(year=int_year,page=page,paginate_by=self.get_paginate_by())
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

        return super(self.__class__,self).get_context_data(**context)

    def dispatch(self, request, *args, **kwargs):
        if 'as_csv' in kwargs:
            self.as_csv = True
        return super(self.__class__, self).dispatch(request, *args, **kwargs)

    def render_to_response(self, context, **response_kwargs):
        if self.as_csv:
            return self.render_to_csv(context)
        return super(self.__class__, self).render_to_response(context, **response_kwargs)

    def render_to_csv(self, context):
        statement = context['statement']
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="financialStatementByEvent.csv"'

        writer = csv.writer(response, csv.excel)
        response.write(u'\ufeff'.encode('utf8'))  # BOM (optional...Excel needs it to open UTF-8 file properly)

        header_list = [
            _('Event'),
            _('Month'),
            _('Registrations: Total'),
            _('Registrations: Leads'),
            _('Registrations: Follows'),
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
                x['registrations']['total'],
                x['registrations']['leads'],
                x['registrations']['follows'],
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


class FinancesByMonthView(PermissionRequiredMixin, TemplateView):
    permission_required = 'financial.view_finances_bymonth'
    cache_timeout = 3600
    template_name = 'financial/finances_bymonth.html'
    as_csv = False
    paginate_by = 24

    def get_paginate_by(self,queryset=None):
        if self.as_csv:
            return 1000
        else:
            return self.paginate_by

    def get(self,request,*args,**kwargs):
        '''
        Allow passing of basis and time limitations
        '''
        try:
            year = int(self.kwargs.get('year'))
        except (ValueError, TypeError):
            year = getIntFromGet(request,'year')

        kwargs.update({
            'year': year,
            'basis': request.GET.get('basis'),
        })

        if kwargs.get('basis') not in EXPENSE_BASES.keys():
            kwargs['basis'] = 'accrualDate'

        return super(self.__class__,self).get(request,*args,**kwargs)

    def get_context_data(self,**kwargs):
        context = {}

        # Determine the period over which the statement should be produced.
        year = kwargs.get('year')

        eligible_years = list(set([x.year for x in ExpenseItem.objects.values_list('accrualDate',flat=True).distinct()]))
        eligible_years.sort(reverse=True)

        if year and year not in eligible_years:
            raise Http404(_("Invalid year."))

        context.update({
            'basis': kwargs.get('basis'),
            'basis_name': EXPENSE_BASES[kwargs.get('basis')],
            'year': year,
            'current_year': year or 'all',
            'eligible_years': eligible_years,
        })

        page = self.kwargs.get('page') or self.request.GET.get('page') or 1

        context['statement'] = prepareFinancialStatement(year=year)
        paginator, page_obj, statementByMonth, is_paginated = prepareStatementByMonth(year=year,basis=context['basis'],page=page,paginate_by=self.get_paginate_by())
        context.update({
            'paginator': paginator,
            'page_obj': page_obj,
            'is_paginated': is_paginated,
        })
        context['statement']['statementByMonth'] = statementByMonth

        return super(self.__class__,self).get_context_data(**context)

    def dispatch(self, request, *args, **kwargs):
        if 'as_csv' in kwargs:
            self.as_csv = True
        return super(self.__class__, self).dispatch(request, *args, **kwargs)

    def render_to_response(self, context, **response_kwargs):
        if self.as_csv:
            return self.render_to_csv(context)
        return super(self.__class__, self).render_to_response(context, **response_kwargs)

    def render_to_csv(self, context):
        statement = context['statement']
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="financialStatementByMonth.csv"'

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

        for x in statement['statementByMonth']:
            this_row_data = [
                x['month_name'],
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


class FinancialDetailView(FinancialContextMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'financial.view_finances_detail'
    template_name = 'financial/finances_detail.html'

    def get(self,request,*args,**kwargs):
        '''
        Pass any permissable GET data.  URL parameters override GET parameters
        '''
        try:
            year = int(self.kwargs.get('year'))
        except (ValueError, TypeError):
            year = getIntFromGet(request,'year')

        if self.kwargs.get('month'):
            try:
                month = int(self.kwargs.get('month'))
            except (ValueError, TypeError):
                try:
                    month = list(month_name).index(self.kwargs.get('month').title())
                except (ValueError, TypeError):
                    month = None
        else:
            month = getIntFromGet(request,'month')

        kwargs.update({
            'year': year,
            'month': month,
            'startDate': getDateTimeFromGet(request,'startDate'),
            'endDate': getDateTimeFromGet(request,'endDate'),
            'basis': request.GET.get('basis'),
        })

        if kwargs.get('basis') not in EXPENSE_BASES.keys():
            kwargs['basis'] = 'accrualDate'

        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)

    def get_context_data(self,**kwargs):
        context = kwargs.copy()
        timeFilters = {}

        # Determine the period over which the statement should be produced.
        year = kwargs.get('year')
        month = kwargs.get('month')
        startDate = kwargs.get('startDate')
        endDate = kwargs.get('endDate')

        basis = kwargs.get('basis')

        context.update({
            'basis': basis,
            'basis_name': EXPENSE_BASES[basis],
            'rangeTitle': '',
        })

        if startDate:
            timeFilters['%s__gte' % basis] = startDate
            context['rangeType'] = 'Date Range'
            context['rangeTitle'] += _('From %s' % startDate.strftime('%b. %d, %Y'))
        if endDate:
            timeFilters['%s__lt' % basis] = endDate
            context['rangeType'] = 'Date Range'
            context['rangeTitle'] += _('To %s' % endDate.strftime('%b. %d, %Y'))

        if not startDate and not endDate:
            if month and year:
                end_month = ((month) % 12) + 1
                end_year = year
                if end_month == 1:
                    end_year = year + 1

                timeFilters['%s__gte' % basis] = ensure_timezone(datetime(year,month,1))
                timeFilters['%s__lt' % basis] = ensure_timezone(datetime(end_year,end_month,1))

                context['rangeType'] = 'Month'
                context['rangeTitle'] = '%s %s' % (month_name[month], year)

            elif year:
                timeFilters['%s__gte' % basis] = ensure_timezone(datetime(year,1,1))
                timeFilters['%s__lt' % basis] = ensure_timezone(datetime(year + 1,1,1))

                context['rangeType'] = 'Year'
                context['rangeTitle'] = '%s' % year
            else:
                # Assume year to date if nothing otherwise specified
                timeFilters['%s__gte' % basis] = ensure_timezone(datetime(timezone.now().year,1,1))
                timeFilters['%s__lt' % basis] = ensure_timezone(datetime(timezone.now().year + 1,1,1))

                context['rangeType'] = 'YTD'
                context['rangeTitle'] = _('Calendar Year To Date')

        context['startDate'] = timeFilters['%s__gte' % basis]
        context['endDate'] = timeFilters['%s__lt' % basis]

        # Revenues are booked on receipt basis, not payment/approval basis
        rev_timeFilters = timeFilters.copy()
        rev_basis = basis

        if basis in ['paymentDate', 'approvalDate']:
            rev_basis = 'receivedDate'
            rev_timeFilters['receivedDate__gte'] = rev_timeFilters['%s__gte' % basis]
            rev_timeFilters['receivedDate__lt'] = rev_timeFilters['%s__lt' % basis]
            del rev_timeFilters['%s__gte' % basis]
            del rev_timeFilters['%s__lt' % basis]

        expenseItems = ExpenseItem.objects.filter(**timeFilters).annotate(net=F('total') + F('adjustments') + F('fees'),basisDate=Min(basis)).order_by(basis)
        revenueItems = RevenueItem.objects.filter(**rev_timeFilters).annotate(net=F('total') + F('adjustments') - F('fees'),basisDate=Min(rev_basis)).order_by(rev_basis)

        context['expenseItems'] = expenseItems
        context['revenueItems'] = revenueItems

        # Registration revenues, instruction and venue expenses
        # are broken out separately.

        context.update({
            'instructionExpenseItems': expenseItems.filter(category__in=[getConstant('financial__classInstructionExpenseCat'),getConstant('financial__assistantClassInstructionExpenseCat')]).order_by('payToUser__last_name','payToUser__first_name'),
            'venueExpenseItems': expenseItems.filter(category=getConstant('financial__venueRentalExpenseCat')).order_by('payToLocation__name'),
            'otherExpenseItems': expenseItems.exclude(category__in=[getConstant('financial__classInstructionExpenseCat'),getConstant('financial__assistantClassInstructionExpenseCat'),getConstant('financial__venueRentalExpenseCat')]).order_by('category'),
            'expenseCategoryTotals': ExpenseCategory.objects.filter(expenseitem__in=expenseItems).annotate(category_total=Sum('expenseitem__total'),category_adjustments=Sum('expenseitem__adjustments'),category_fees=Sum('expenseitem__fees')).annotate(category_net=F('category_total') + F('category_adjustments') + F('category_fees')),
        })
        context.update({
            'instructionExpenseInstructorTotals': User.objects.filter(payToUser__in=context['instructionExpenseItems']).annotate(instructor_total=Sum('payToUser__total'),instructor_adjustments=Sum('payToUser__adjustments'),instructor_fees=Sum('payToUser__fees')).annotate(instructor_net=F('instructor_total') + F('instructor_adjustments') + F('instructor_fees')),
            'instructionExpenseOtherTotal': context['instructionExpenseItems'].filter(payToUser__isnull=True).annotate(net=F('total') + F('adjustments') + F('fees')).aggregate(instructor_total=Sum('total'),instructor_adjustments=Sum('adjustments'),instructor_fees=Sum('fees'),instructor_net=Sum('net')),

            'venueExpenseVenueTotals': Location.objects.filter(expenseitem__in=context['venueExpenseItems']).annotate(location_total=Sum('expenseitem__total'),location_adjustments=Sum('expenseitem__adjustments'),location_fees=Sum('expenseitem__fees')).annotate(location_net=F('location_total') + F('location_adjustments') + F('location_fees')),
            'venueExpenseOtherTotal': context['venueExpenseItems'].filter(payToLocation__isnull=True).annotate(location_net=F('total') + F('adjustments') + F('fees')).aggregate(location_total=Sum('total'),location_adjustments=Sum('adjustments'),location_fees=Sum('fees'),location_net=Sum('net')),

            'totalInstructionExpenses': sum([x.category_net or 0 for x in context['expenseCategoryTotals'].filter(id__in=[getConstant('financial__classInstructionExpenseCat').id,getConstant('financial__assistantClassInstructionExpenseCat').id])]),
            'totalVenueExpenses': sum([x.category_net or 0 for x in context['expenseCategoryTotals'].filter(id=getConstant('financial__venueRentalExpenseCat').id)]),
            'totalOtherExpenses': sum([x.category_net or 0 for x in context['expenseCategoryTotals'].exclude(id__in=[getConstant('financial__classInstructionExpenseCat').id,getConstant('financial__assistantClassInstructionExpenseCat').id,getConstant('financial__venueRentalExpenseCat').id])]),

            'totalExpenses': sum([x.category_net or 0 for x in context['expenseCategoryTotals']]),
        })

        context.update({
            'registrationRevenueItems': revenueItems.filter(category=getConstant('financial__registrationsRevenueCat')).order_by('-event__startTime','event__uuid'),
            'otherRevenueItems': revenueItems.exclude(category=getConstant('financial__registrationsRevenueCat')).order_by('category'),
            'revenueCategoryTotals': RevenueCategory.objects.filter(revenueitem__in=revenueItems).annotate(category_total=Sum('revenueitem__total'),category_adjustments=Sum('revenueitem__adjustments'),category_fees=Sum('revenueitem__fees')).annotate(category_net=F('category_total') + F('category_adjustments') - F('category_fees')),
        })
        context.update({
            'registrationRevenueEventTotals': Event.objects.filter(eventregistration__invoiceitem__revenueitem__in=context['registrationRevenueItems']).annotate(event_total=Sum('eventregistration__invoiceitem__revenueitem__total'),event_adjustments=Sum('eventregistration__invoiceitem__revenueitem__adjustments'),event_fees=Sum('eventregistration__invoiceitem__revenueitem__fees')).annotate(event_net=F('event_total') + F('event_adjustments') - F('event_fees')),
            'registrationRevenueOtherTotal': context['registrationRevenueItems'].filter(invoiceItem__finalEventRegistration__isnull=True).annotate(event_net=F('total') + F('adjustments') - F('fees')).aggregate(event_total=Sum('total'),event_adjustments=Sum('adjustments'),event_fees=Sum('fees'),event_net=Sum('net')),

            'totalRegistrationRevenues': sum([x.category_net or 0 for x in context['revenueCategoryTotals'].filter(id=getConstant('financial__registrationsRevenueCat').id)]),
            'totalOtherRevenues': sum([x.category_net or 0 for x in context['revenueCategoryTotals'].exclude(id=getConstant('financial__registrationsRevenueCat').id)]),
            'totalRevenues': sum([x.category_net or 0 for x in context['revenueCategoryTotals']]),
        })

        context.update({
            'netProfit': context['totalRevenues'] - context['totalExpenses'],
        })

        return super(self.__class__,self).get_context_data(**context)


class CompensationRuleUpdateView(SuccessMessageMixin, AdminSuccessURLMixin, PermissionRequiredMixin, FinancialContextMixin, FormView):
    '''
    This view is for an admin action to repeat events.
    '''
    template_name = 'financial/update_staff_compensation_rules.html'
    form_class = CompensationRuleUpdateForm
    permission_required = 'core.change_staffmember'
    success_message = _('Staff member compensation rules updated successfully.')

    def dispatch(self, request, *args, **kwargs):
        ids = request.GET.get('ids')
        ct = getIntFromGet(request,'ct')

        try:
            contentType = ContentType.objects.get(id=ct)
            self.objectClass = contentType.model_class()
        except (ValueError, ObjectDoesNotExist):
            return HttpResponseBadRequest(_('Invalid content type passed.'))

        # This view only deals with subclasses of StaffMember (Instructor, etc.)
        if not isinstance(self.objectClass(),StaffMember):
            return HttpResponseBadRequest(_('Invalid content type passed.'))

        try:
            self.queryset = self.objectClass.objects.filter(id__in=[int(x) for x in ids.split(',')])
        except ValueError:
            return HttpResponseBadRequest(_('Invalid ids passed'))

        return super(CompensationRuleUpdateView,self).dispatch(request,*args,**kwargs)

    def get_context_data(self,**kwargs):
        context = super(CompensationRuleUpdateView,self).get_context_data(**kwargs)
        context.update({
            'staffmembers': self.queryset,
            'rateRuleValues': RepeatedExpenseRule.RateRuleChoices.values,
        })

        return context

    def form_valid(self, form):
        category = form.cleaned_data.pop('category',None)

        for staffmember in self.queryset:
            staffmember.expenserules.update_or_create(
                category=category,
                defaults=form.cleaned_data,
            )

        return super(CompensationRuleUpdateView,self).form_valid(form)


class AllExpensesViewCSV(PermissionRequiredMixin, View):
    permission_required = 'financial.export_financial_data'

    def dispatch(self, request, *args, **kwargs):
        all_expenses = ExpenseItem.objects.order_by('-paid','-approved','-submissionDate')
        return getExpenseItemsCSV(all_expenses,scope='all')


class AllRevenuesViewCSV(PermissionRequiredMixin, View):
    permission_required = 'financial.export_financial_data'

    def dispatch(self, request, *args, **kwargs):
        all_revenues = RevenueItem.objects.order_by('-submissionDate')
        return getRevenueItemsCSV(all_revenues)
