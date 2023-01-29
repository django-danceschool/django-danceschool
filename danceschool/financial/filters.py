from django.db.models import Q, Subquery, OuterRef, Sum, FloatField
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _

from django_filters import rest_framework as rest_filters
from django_filters import CharFilter, DateFromToRangeFilter

from .models import ExpenseItem, RevenueItem, TransactionParty


class ExpenseItemFilter(rest_filters.FilterSet):
    description = CharFilter(lookup_expr='icontains')
    paymentDate = DateFromToRangeFilter()
    accrualDate = DateFromToRangeFilter()
    submissionDate = DateFromToRangeFilter()

    class Meta:
        model = ExpenseItem
        fields = [
            'category', 'paymentMethod', 'event', 'expenseRule', 'payTo',
            'reimbursement', 'approved', 'paid'
        ]


class RevenueItemFilter(rest_filters.FilterSet):
    description = CharFilter(lookup_expr='icontains')
    receivedDate = DateFromToRangeFilter()
    accrualDate = DateFromToRangeFilter()
    submissionDate = DateFromToRangeFilter()

    class Meta:
        model = RevenueItem
        fields = [
            'category', 'paymentMethod', 'event', 'invoiceNumber',
            'invoiceItem', 'receivedFrom', 'currentlyHeldBy', 'received'
        ]


class TransactionPartyFilter(rest_filters.FilterSet):
    name = CharFilter(lookup_expr='istartswith')
    accrualDate = DateFromToRangeFilter(label=_('Accrual Date'), method='subqueryDateFilter')
    paymentDate = DateFromToRangeFilter(label=_('Payment Date'), method='subqueryDateFilter')

    def subqueryDateFilter(self, queryset, name, value):
        expenseFilters = {'payTo': OuterRef('pk')}
        revFilters = {'receivedFrom': OuterRef('pk')}

        rev_name = 'receivedDate' if name == 'paymentDate' else name

        if value:
            if value.start is not None and value.stop is not None:
                expenseFilters[f'{name}__range'] = (value.start, value.stop)
                revFilters[f'{rev_name}__range'] = (value.start, value.stop)
            elif value.start is not None:
                expenseFilters[f'{name}__gte'] = value.start
                revFilters[f'{rev_name}__gte'] = value.start
            elif value.stop is not None:
                expenseFilters[f'{name}__lte'] = value.stop
                revFilters[f'{rev_name}__lte'] = value.stop

        expenseTotals = ExpenseItem.objects.filter(**expenseFilters).annotate(
            paidTotal=Sum('total', filter=Q(paid=True)),
            unpaidTotal=Sum('total', filter=Q(paid=False)),
            reimbursementTotal=Sum('total', filter=Q(reimbursement=True)),
        )
        revenueTotals = RevenueItem.objects.filter(**revFilters).annotate(
            receivedTotal=Sum('total', filter=Q(received=True)),
        )

        return queryset.annotate(
            expensePaidTotal=Coalesce(
                Subquery(expenseTotals.values('paidTotal')), 0, output_field=FloatField()
            ),
            expenseUnpaidTotal=Coalesce(
                Subquery(expenseTotals.values('unpaidTotal')), 0, output_field=FloatField()
            ),
            reimbursementTotal=Coalesce(
                Subquery(expenseTotals.values('reimbursementTotal')), 0, output_field=FloatField()
            ),
            revenueReceivedTotal=Coalesce(
                Subquery(revenueTotals.values('receivedTotal')), 0, output_field=FloatField()
            )
        )

    class Meta:
        model = TransactionParty
        fields = []
