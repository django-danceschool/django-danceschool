from django.dispatch import receiver
from django.db.models.signals import post_save, m2m_changed
from django.utils.translation import ugettext_lazy as _

import sys
import logging

from danceschool.core.models import EventStaffMember, EventOccurrence, InvoiceItem, Invoice
from danceschool.core.constants import getConstant

from .models import ExpenseItem, RevenueItem, RevenueCategory


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(m2m_changed, sender=EventStaffMember.occurrences.through)
def modifyExistingExpenseItemsForEventStaff(sender,instance,**kwargs):
    if 'loaddata' in sys.argv or ('raw' in kwargs and kwargs['raw']):
        return
    if kwargs.get('action',None) != 'post_add':
        return

    logger.debug('ExpenseItem signal fired for EventStaffMember %s.' % instance.pk)
    staff_expenses = ExpenseItem.objects.filter(eventstaffmember__pk=instance.pk)

    if staff_expenses:
        logger.debug('Updating existing expense items for event staff member.')
        # Fill in the updated hours and the updated total.  Set the expense item
        # to unapproved.
        for expense in staff_expenses:
            logger.debug('Updating expense item %s.' % expense.id)
            expense.hours = instance.netHours
            expense.total = expense.hours * expense.wageRate
            expense.approved = False
            expense.save()

    if hasattr(instance,'replacedStaffMember'):
        logger.debug('Adjusting totals for replaced event staff member.')
        replaced_expenses = ExpenseItem.objects.filter(eventstaffmember=instance.replacedStaffMember)

        # Fill in the updated hours and the updated total.  Set the expense item
        # to unapproved.
        for expense in replaced_expenses:
            logger.debug('Updating expense item %s' % expense.id)
            expense.hours = expense.eventstaffmember.netHours
            expense.total = expense.hours * expense.wageRate
            expense.approved = False
            expense.save()


@receiver(post_save, sender=EventOccurrence)
def modifyExistingExpenseItemsForSeriesClass(sender,instance,**kwargs):
    if 'loaddata' in sys.argv or ('raw' in kwargs and kwargs['raw']):
        return

    logger.debug('ExpenseItem signal fired for EventOccurrence %s.' % instance.id)

    staff_expenses = ExpenseItem.objects.filter(eventstaffmember__in=instance.eventstaffmember_set.all())

    # Fill in the updated hours and the updated total.  Set the expense item
    # to unapproved.
    for expense in staff_expenses:
        expense.hours = expense.eventstaffmember.netHours
        expense.total = expense.hours * expense.wageRate
        expense.approved = False
        expense.save()


@receiver(post_save, sender=InvoiceItem)
def createRevenueItemForInvoiceItem(sender,instance,**kwargs):
    if 'loaddata' in sys.argv or ('raw' in kwargs and kwargs['raw']):
        return

    logger.debug('RevenueItem signal fired for InvoiceItem %s.' % instance.id)

    received_status = (instance.invoice.status == Invoice.PaymentStatus.paid)

    related_item = getattr(instance, 'revenueitem', None)
    if not related_item:
        related_item = RevenueItem.objects.create(
            invoiceItem=instance,
            invoiceNumber=instance.id,
            grossTotal=instance.grossTotal,
            total=instance.total,
            adjustments=instance.adjustments,
            fees=instance.fees,
            taxes=instance.taxes,
            category=getConstant('financial__registrationsRevenueCat'),
            submissionUser=instance.invoice.submissionUser,
            currentlyHeldBy=instance.invoice.collectedByUser,
            received=received_status,
            paymentMethod=instance.invoice.get_payment_method(),
            description=_('Registration invoice %s' % instance.id)
        )
        logger.debug('RevenueItem created.')
    else:
        # Check that the existing revenueItem is still correct
        saveFlag = False

        for field in ['grossTotal','total','adjustments','fees','taxes']:
            if getattr(related_item,field) != getattr(instance,field):
                setattr(related_item,field,getattr(instance,field))
                saveFlag = True

        if related_item.received != received_status:
            related_item.received = received_status
            related_item.paymentMethod = instance.invoice.get_payment_method()
            saveFlag = True

        if saveFlag:
            related_item.save()
            logger.info('RevenueItem associated with InvoiceItem %s updated.' % instance.id)
