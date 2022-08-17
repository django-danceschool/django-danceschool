'''
This file contains custom managers and querysets for various core models.
'''
from django.db import models

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
        return InvoiceQuerySet(self.model, using=self._db)
