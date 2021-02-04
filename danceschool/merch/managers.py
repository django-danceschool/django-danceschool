'''
This file contains custom managers and querysets for the MerchOrder model
'''
from django.db import models

from danceschool.core.models import Invoice


class MerchOrderQuerySet(models.QuerySet):
    '''
    Only unsubmitted orders may be deleted.
    '''

    def delete(self):
        self.exclude(models.Q(invoice__status__in=[
            Invoice.PaymentStatus.needsCollection, Invoice.PaymentStatus.cancelled
        ]) | models.Q(status=self.model.OrderStatus.unsubmitted)).update(
            status=self.model.OrderStatus.cancelled
        )
        filtered_query = self.__deepcopy__({}).filter(
            status=self.model.OrderStatus.unsubmitted
        )
        super(MerchOrderQuerySet, filtered_query).delete()


class MerchOrderManager(models.Manager):
    ''' Use MerchOrderQuerySet to allow deletion only of unsubmitted orders. '''
    def get_queryset(self):
        return MerchOrderQuerySet(self.model, using=self._db)
