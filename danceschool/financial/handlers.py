from django.dispatch import receiver
from django.db.models.signals import post_save, m2m_changed
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _

from datetime import datetime
import sys
import logging

from danceschool.core.models import EventStaffMember, EventOccurrence, EventRegistration
from danceschool.core.constants import getConstant
from danceschool.vouchers.models import Voucher

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


@receiver(post_save, sender=EventRegistration)
def createRevenueItemForEventRegistration(sender,instance,**kwargs):
    if 'loaddata' in sys.argv or ('raw' in kwargs and kwargs['raw']):
        return

    logger.debug('RevenueItem signal fired for EventRegistration %s.' % instance.id)

    if not instance.revenueitem_set.all():
        logger.debug('Identifying and matching revenue item for EventRegistration %s.' % instance.id)
        this_item = RevenueItem.objects.filter(
            Q(invoiceNumber='%s_event_%s_%s' % (instance.registration.invoiceNumber, instance.event.id, instance.matchingTemporaryRegistration.id)) |
            Q(invoiceNumber='%s_series_%s_%s' % (instance.registration.invoiceNumber, instance.event.id, instance.matchingTemporaryRegistration.id))
        ).first()

        if this_item:
            this_item.eventregistration = instance
            this_item.save()
            logger.debug('RevenueItem matched.')
        elif not instance.registration.paidOnline and instance.netPrice != 0:
            ''' Create revenue items for new cash registration payments '''
            RevenueItem.objects.create(
                invoiceNumber=instance.registration.invoiceNumber,
                grossTotal=instance.price,
                total=instance.netPrice,
                category=RevenueCategory.objects.get(id=getConstant('financial__registrationsRevenueCatID')),
                eventregistration=instance,
                submissionUser=instance.registration.submissionUser,
                currentlyHeldBy=instance.registration.collectedByUser,
                description=_('Cash event registration %s' % instance.id)
            )
            logger.debug('RevenueItem created.')
        else:
            logger.warning('Online registration without associated RevenueItem.  Check records for errors.')
    else:
        logger.debug('Registration already matched to revenue item.')


@receiver(post_save, sender=Voucher)
def createRevenueItemForVoucher(sender,instance,**kwargs):
    if 'loaddata' in sys.argv or ('raw' in kwargs and kwargs['raw']):
        return

    logger.debug('RevenueItem signal fired for Voucher %s: %s.' % (instance.id,instance.voucherId))

    submissionUser = None
    received = True

    if not hasattr(instance,'revenueitem') and instance.category and instance.category.id == getConstant('vouchers__giftCertCategoryID'):
        logger.debug('Creating RevenueItem for new Voucher %s.' % instance.id)

        this_category = RevenueCategory.objects.get(id=getConstant('financial__giftCertRevenueCatID'))
        revenue_description = _('Gift Certificate Purchase ' + str(instance.voucherId))
        RevenueItem.objects.create(
            purchasedVoucher=instance,
            category=this_category,
            description=revenue_description,
            submissionUser=submissionUser,
            grossTotal=instance.originalAmount,
            total=instance.originalAmount,
            received=received,
            receivedDate=datetime.now())
    elif instance.category and instance.category.id == getConstant('vouchers__giftCertCategoryID') and instance.revenueitem.adjustments != instance.refundAmount:
        logger.debug('Adjusting RevenueItem for Voucher %s.' % instance.id)

        instance.revenueitem.adjustments = -1 * instance.refundAmount
        instance.revenueitem.save()
    elif instance.category and instance.category.id == getConstant('vouchers__giftCertCategoryID'):
        logger.debug('No change to RevenueItem for Voucher %s.' % instance.id)
    else:
        logger.debug('Voucher is from category that is not counted as revenue.')
