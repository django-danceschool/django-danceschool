from django.db import models
from django.db.models import F

from danceschool.core.utils.tax import netRevenueExpression


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
            net=netRevenueExpression('buyerPaysSalesTax'),
        )
