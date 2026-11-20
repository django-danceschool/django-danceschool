'''
This file contains custom managers and querysets for various core models.
'''
from django.db import models
from django.db.models import Q

from .utils.tax import netRevenueExpression


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
    '''
    Use InvoiceQuerySet to allow deletion only of preliminary invoices.  The
    net revenue of an invoice is not annotated, because the tax that is
    refunded is added up over its items (see Invoice.netRevenue).
    '''
    def get_queryset(self):
        return InvoiceQuerySet(self.model, using=self._db).annotate(
            _items_editable=Q(status__in=['0', 'U']),
        )


class InvoiceItemManager(models.Manager):
    ''' Add net annotation '''
    def get_queryset(self):
        return super().get_queryset().select_related('invoice').annotate(
            net=netRevenueExpression('invoice__buyerPaysSalesTax'),
        )
