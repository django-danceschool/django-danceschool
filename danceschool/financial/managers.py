from django.db import models
from django.db.models import F, Case, When, Q


class ExpenseItemManager(models.Manager):
    ''' Adds net expense annotation. '''

    def get_queryset(self):
        return super().get_queryset().annotate(
            net = (
                F('total') + F('adjustments') + F('fees')
            )
        )


class RevenueItemManager(models.Manager):
    ''' Adds net revenue annotation. '''

    def get_queryset(self):
        return super().get_queryset().annotate(
            net = (
                F('total') + F('adjustments') - F('fees') -
                Case(When(Q(buyerPaysSalesTax=False), then=F('taxes')), default=0.0)
            )
        )
