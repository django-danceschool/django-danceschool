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


class SeriesTeacherManager(models.Manager):
    '''
    Limits SeriesTeacher queries to only staff reported as teachers, and ensures that
    these individuals are reported as teachers when created.
    '''

    def get_queryset(self):
        return super().get_queryset().filter(
            category=getConstant('general__eventStaffCategoryInstructor')
        )

    def create(self, **kwargs):
        kwargs.update({
            'category': getConstant('general__eventStaffCategoryInstructor').id,
            'occurrences': kwargs.get('event').eventoccurrence_set.all(),
        })
        return super().create(**kwargs)


class SubstituteTeacherManager(models.Manager):
    '''
    Limits SeriesTeacher queries to only staff reported as teachers, and ensures that
    these individuals are reported as teachers when created.
    '''

    def get_queryset(self):
        return super().get_queryset().filter(
            category=getConstant('general__eventStaffCategorySubstitute')
        )

    def create(self, **kwargs):
        kwargs.update({
            'category': getConstant('general__eventStaffCategorySubstitute').id})
        return super().create(**kwargs)


class EventDJManager(models.Manager):
    '''
    Limits Dj queries to only staff reported as DJs, and ensures that
    these individuals are reported as DJs when created.
    '''

    def get_queryset(self):
        return super().get_queryset().filter(
            category=getConstant('general__eventStaffCategoryDJ')
        )

    def create(self, **kwargs):
        kwargs.update({
            'category': getConstant('general__eventStaffCategoryDJ').id,
        })
        return super().create(**kwargs)


class SeriesStaffManager(models.Manager):
    '''
    Limits SeriesStaff queries to exclude SeriesTeachers and SubstituteTeachers
    '''

    def get_queryset(self):
        return super().get_queryset().exclude(
            category__in=[
                getConstant('general__eventStaffCategoryInstructor'),
                getConstant('general__eventStaffCategorySubstitute'),
            ],
        )
