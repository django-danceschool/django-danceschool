from django.views.generic import View
from django.db.models import Sum, Subquery, OuterRef, Count

from braces.views import PermissionRequiredMixin

from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination

from danceschool.core.models import Event, EventCheckIn
from danceschool.core.mixins import BrowsableRestMixin, CSVRestMixin
from danceschool.core.permissions import DjangoModelPermissions, BaseRequiredPermission

from ..models import ExpenseItem, RevenueItem, TransactionParty
from ..helpers.csv import getExpenseItemsCSV, getRevenueItemsCSV
from ..serializers import (
    ExpenseItemSerializer, RevenueItemSerializer, TransactionPartySerializer,
    EventFinancialSerializer,
)
from ..filters import (
    ExpenseItemFilter, RevenueItemFilter, TransactionPartyFilter,
    EventFinancialFilter,
)


class ExportPermission(BaseRequiredPermission):
    """
    Check if the user has permission to export financial data
    """
    permission_required = 'financial.export_financial_data'


class FinancialPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000
    ordering = '-accrualDate'


class ExpenseItemViewSet(BrowsableRestMixin, CSVRestMixin, viewsets.ModelViewSet):
    queryset = ExpenseItem.objects.all().order_by('-accrualDate')
    serializer_class = ExpenseItemSerializer
    permission_classes = [DjangoModelPermissions&ExportPermission]
    filterset_class = ExpenseItemFilter
    pagination_class = FinancialPagination


class RevenueItemViewSet(BrowsableRestMixin, CSVRestMixin, viewsets.ModelViewSet):
    queryset = RevenueItem.objects.all().order_by('-accrualDate')
    serializer_class = RevenueItemSerializer
    permission_classes = [DjangoModelPermissions&ExportPermission]
    filterset_class = RevenueItemFilter
    pagination_class = FinancialPagination


class TransactionPartyViewSet(
    BrowsableRestMixin, CSVRestMixin, viewsets.ReadOnlyModelViewSet
):
    queryset = TransactionParty.objects.all().order_by('name')
    serializer_class = TransactionPartySerializer
    permission_classes = [DjangoModelPermissions&ExportPermission]
    filterset_class = TransactionPartyFilter


class EventFinancialViewSet(
    BrowsableRestMixin, CSVRestMixin, viewsets.ReadOnlyModelViewSet
):
    serializer_class = EventFinancialSerializer
    permission_classes = [DjangoModelPermissions&ExportPermission]
    filterset_class = EventFinancialFilter
    queryset = Event.objects.all().order_by('-startTime')

    def get_queryset(self):
        revs = RevenueItem.objects.filter(event=OuterRef('pk'))
        expenses = ExpenseItem.objects.filter(event=OuterRef('pk'))

        revs_agg = revs.values('event').annotate(
            sum_total=Sum('total'), sum_adjustments=Sum('adjustments'),
            sum_taxes=Sum('taxes'), sum_fees=Sum('fees')
        )

        cash_revs = revs.filter(
            paymentMethod__iexact='cash', received=True
        ).values('paymentMethod').annotate(
            sum_total=Sum('total'), sum_adjustments=Sum('adjustments'),
            sum_taxes=Sum('taxes'), sum_fees=Sum('fees')
        )
        other_revs = revs.filter(received=True).exclude(
            paymentMethod__iexact='cash'
        ).values('event').annotate(
            sum_total=Sum('total'), sum_adjustments=Sum('adjustments'),
            sum_taxes=Sum('taxes'), sum_fees=Sum('fees')
        )

        checkins = EventCheckIn.objects.filter(
            event=OuterRef('pk'), cancelled=False
        )
        event_checkins = checkins.filter(checkInType='E').values('event').annotate(count=Count('pk'))
        occurrence_checkins = checkins.filter(checkInType='O').values('event').annotate(count=Count('pk'))

        qs = super().get_queryset() or Event.objects.all()
        return qs.annotate(
            revenue_total=Subquery(revs_agg.values('sum_total')),
            revenue_adjustments=Subquery(revs_agg.values('sum_adjustments')),
            revenue_taxes=Subquery(revs_agg.values('sum_taxes')),
            revenue_fees=Subquery(revs_agg.values('sum_fees')),
            cash_received_total=Subquery(cash_revs.values('sum_total')),
            cash_received_adjustments=Subquery(cash_revs.values('sum_adjustments')),
            cash_received_taxes=Subquery(cash_revs.values('sum_taxes')),
            cash_received_fees=Subquery(cash_revs.values('sum_fees')),
            other_received_total=Subquery(other_revs.values('sum_total')),
            other_received_adjustments=Subquery(other_revs.values('sum_adjustments')),
            other_received_taxes=Subquery(other_revs.values('sum_taxes')),
            other_received_fees=Subquery(other_revs.values('sum_fees')),
            expense_total=Subquery(expenses.values('event').annotate(
                sum_total=Sum('total')
            ).values('sum_total')),
            expense_paid_total=Subquery(expenses.filter(paid=True).values('event').annotate(
                sum_total=Sum('total')
            ).values('sum_total')),
            event_checkins=Subquery(event_checkins.values('count')),
            occurrence_checkins=Subquery(occurrence_checkins.values('count')),
        ).order_by('-startTime')


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
