'''
This file contains custom managers and querysets for various core models.
'''
from django.db import models
from django.db.models import Case, When, Q, F

from danceschool.core.constants import getConstant


class InvoiceQuerySet(models.QuerySet):
    '''
    Only preliminary invoices may be deleted.  Paid invoices are ignored, while
    all other invoices are cancelled.
    '''

    def delete(self):
        self.exclude(status__in=[
            self.model.PaymentStatus.preliminary, self.model.PaymentStatus.paid
        ]).update(
            status=self.model.PaymentStatus.cancelled
        )
        filtered_query = self.__deepcopy__({}).filter(
            status=self.model.PaymentStatus.preliminary
        )
        super(InvoiceQuerySet, filtered_query).delete()


class InvoiceManager(models.Manager):
    ''' Use InvoiceQuerySet to allow deletion only of preliminary invoices. '''
    def get_queryset(self):
        return InvoiceQuerySet(self.model, using=self._db).annotate(
            net = (
                F('total') + F('adjustments') - F('fees') -
                Case(When(Q(buyerPaysSalesTax=False), then=F('taxes')), default=0.0)
            )
        )


class InvoiceItemManager(models.Manager):
    ''' Add net annotation '''
    def get_queryset(self):
        return super().get_queryset().select_related('invoice').annotate(
            net = (
                F('total') + F('adjustments') - F('fees') -
                Case(When(Q(invoice__buyerPaysSalesTax=False), then=F('taxes')), default=0.0)
            )
        )
