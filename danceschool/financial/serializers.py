from django.contrib.auth.models import User, Group
from rest_framework import serializers

from danceschool.core.models import Event
from .models import ExpenseItem, RevenueItem, TransactionParty


class ExpenseItemSerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField()
    expenseRule = serializers.StringRelatedField()
    payTo = serializers.StringRelatedField()

    class Meta:
        model = ExpenseItem
        fields = [
            'id', 'description', 'category', 'hours', 'wageRate', 'total',
            'adjustments', 'fees', 'netExpense', 'paymentMethod', 'comments',
            'event', 'expenseRule', 'periodStart', 'periodEnd', 'payTo',
            'reimbursement', 'approved', 'paid', 'approvalDate', 'paymentDate',
            'accrualDate', 'submissionUser', 'submissionDate',
        ]


class RevenueItemSerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField()
    receivedFrom = serializers.StringRelatedField()
    currentlyHeldBy = serializers.StringRelatedField()

    class Meta:
        model = RevenueItem
        fields = [
            'id', 'description', 'category', 'grossTotal', 'total',
            'adjustments', 'fees', 'taxes', 'netRevenue', 'buyerPaysSalesTax',
            'paymentMethod', 'invoiceNumber', 'comments', 'invoiceItem',
            'event', 'receivedFrom', 'currentlyHeldBy', 'received',
            'receivedDate', 'accrualDate', 'submissionUser', 'submissionDate',
        ]


class TransactionPartySerializer(serializers.ModelSerializer):
    revenueReceivedTotal = serializers.FloatField(read_only=True)
    expensePaidTotal = serializers.FloatField(read_only=True)
    expenseUnpaidTotal = serializers.FloatField(read_only=True)
    reimbursementTotal = serializers.FloatField(read_only=True)

    class Meta:
        model = TransactionParty
        fields = [
            'id', 'name', 'user', 'staffMember', 'staffMember', 'location',
            'revenueReceivedTotal', 'expensePaidTotal',
            'expenseUnpaidTotal', 'reimbursementTotal'
        ]


class EventFinancialSerializer(serializers.ModelSerializer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for f in [
            'revenue_total', 'revenue_adjustments', 'revenue_fees', 'revenue_taxes',
            'cash_received_total', 'cash_received_adjustments',
            'cash_received_taxes', 'cash_received_fees', 'other_received_total',
            'other_received_adjustments', 'other_received_taxes', 'other_received_fees',
            'expense_total', 'expense_paid_total',
        ]:
            setattr(self, f, serializers.FloatField(read_only=True))
            self.fields.update({f: getattr(self, f)})

        for f in ['event_checkins', 'occurrence_checkins']:
            setattr(self, f, serializers.IntegerField(read_only=True))
            self.fields.update({f: getattr(self, f)})

    class Meta:
        model = Event
        fields = [
            'id', 'name', 'startTime', 'endTime', 'location',
            'room', 'session', 'status', 'registrationOpen',
        ]
