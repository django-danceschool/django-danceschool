'''
This file contains custom managers and querysets for various core models.
'''
from django.db import models
from django.db.models import (
    Case, When, Value, Q, F, ExpressionWrapper, Prefetch, Count
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from polymorphic.managers import PolymorphicManager, PolymorphicQuerySet


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
            _items_editable=Q(status__in=['0', 'U']),
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


class EventQuerySet(PolymorphicQuerySet):
    '''
    Make is easier to prefect occurrences and registrations to reduce DB
    overhead.
    '''

    def with_common_annotations(self):
        '''
        Add annotations for registration enabled and other commonly accessed
        attributes for filtering.
        '''
        return self.annotate(
            _registration_enabled=ExpressionWrapper(
                Q(status__in=['O', 'H', 'K']),
                output_field=models.BooleanField()
            ),
            _has_ended=Case(
                When(endTime__lte=timezone.now(), then=Value(True)),
                default=Value(False), output_field=models.BooleanField()
            )
        )

    def with_occurrences(self):
        from danceschool.core.models import EventOccurrence
        return self.prefetch_related(
            Prefetch('eventoccurrence_set', queryset=EventOccurrence.objects.all())
        )

    def with_registrations(self):
        from danceschool.core.models import EventRegistration
        return self.prefetch_related(
            Prefetch(
                'eventregistration_set',
                queryset=EventRegistration.objects.select_related('registration')
            )
        ).annotate(
            _total_registered=Count(
                'eventregistration_set',
                filter=(Q(cancelled=False) & Q(dropIn=False) & Q(registration__final=True)),
                distinct=True
            )
        ).annotate(
            _sold_out=ExpressionWrapper(
                F('total_registered') - Coalesce(F('capacity'), 0) >= Value(0),
                output_field=models.BooleanField()
            )
        )


class EventManager(PolymorphicManager.from_queryset(EventQuerySet)):
    '''
    Add annotations for registration enabled and other commonly accessed
    attributes for filtering.
    '''
    def get_queryset(self):
        return super().get_queryset().with_common_annotations()
