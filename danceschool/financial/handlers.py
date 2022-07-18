from django.dispatch import receiver
from django.db.models import Q, Value, CharField, F
from django.db.models.query import QuerySet
from django.db.models.signals import post_save, m2m_changed
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import User

import sys
import logging

from danceschool.core.models import (
    EventStaffMember, EventOccurrence, InvoiceItem, Invoice, StaffMember,
    Location, EventRegistration
)
from danceschool.core.constants import getConstant
from danceschool.core.signals import get_eventregistration_data

from .models import RevenueItem, RepeatedExpenseRule, TransactionParty


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(post_save, sender=EventStaffMember)
@receiver(m2m_changed, sender=EventStaffMember.occurrences.through)
def modifyExistingExpenseItemsForEventStaff(sender, instance, **kwargs):
    if 'loaddata' in sys.argv or ('raw' in kwargs and kwargs['raw']):
        return
    if kwargs.get('action', None) != 'post_add':
        return

    logger.debug('ExpenseItem signal fired for EventStaffMember %s.' % instance.pk)

    new_payTo = TransactionParty.objects.get_or_create(
        staffMember=instance.staffMember,
        defaults={'name': getattr(instance.staffMember, 'fullName', '')}
    )

    staff_expenses = [x.item for x in instance.related_expenses.all()]

    if staff_expenses:
        logger.debug('Updating existing expense item for event staff member.')
        # Fill in the updated hours and the updated total.  Set the expense item
        # to unapproved.
        for expense in staff_expenses:
            logger.debug('Updating expense item %s.' % expense.id)

            if expense.expenseRule == RepeatedExpenseRule.RateRuleChoices.hourly:
                expense.hours = instance.netHours
                expense.total = expense.hours * expense.wageRate
                expense.approved = None

            # Update who the expense should be paid to if the identity of the
            # staff member has changed and the expense is not already paid.
            if not expense.paid:
                expense.payTo = new_payTo
            expense.save()

    if hasattr(instance.replacedStaffMember, 'staffMember'):
        logger.debug('Adjusting totals for replaced event staff member.')

        replaced_expenses = [
            x.item for x in instance.replacedStaffMember.related_expenses.all() if
            x.item.expenseRule == RepeatedExpenseRule.RateRuleChoices.hourly
        ]

        # Fill in the updated hours and the updated total.  Set the expense item
        # to unapproved.
        for expense in replaced_expenses:
            logger.debug('Updating expense item %s' % expense.id)
            expense.hours = instance.replacedStaffMember.netHours
            expense.total = expense.hours * expense.wageRate
            expense.approved = None
            expense.save()


@receiver(post_save, sender=EventOccurrence)
def modifyExistingExpenseItemsForSeriesClass(sender, instance, **kwargs):
    if 'loaddata' in sys.argv or ('raw' in kwargs and kwargs['raw']):
        return

    logger.debug('ExpenseItem signal fired for EventOccurrence %s.' % instance.id)

    event_staff = EventStaffMember.objects.filter(
        Q(event=instance.event) &
        Q(related_expenses__item__expenseRule__applyRateRule=RepeatedExpenseRule.RateRuleChoices.hourly)
    ).distinct().prefetch_related(
        'related_expenses__item', 'related_expenses__item__expenseRule'
    )

    staff_expenses = set()

    for staff in event_staff:
        staff_expenses.update([x.item for x in staff.related_expenses.all()])

    # Fill in the updated hours and the updated total.  Set the expense item
    # to unapproved.
    for expense in staff_expenses:

        this_staff = event_staff.filter(related_expenses__item=expense)
        expense.hours = sum([x.netHours for x in this_staff])
        expense.total = expense.hours * expense.wageRate
        expense.approved = None
        expense.save()


@receiver(post_save, sender=InvoiceItem)
def createRevenueItemForInvoiceItem(sender, instance, **kwargs):
    if 'loaddata' in sys.argv or ('raw' in kwargs and kwargs['raw']):
        return

    logger.debug('RevenueItem signal fired for InvoiceItem %s.' % instance.id)

    if instance.invoice.status == Invoice.PaymentStatus.preliminary:
        logger.debug('Preliminary invoice. No revenue item will be created.')
        return

    received_status = (not instance.invoice.unpaid)

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
            buyerPaysSalesTax=instance.invoice.buyerPaysSalesTax,
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

        for field in ['grossTotal', 'total', 'adjustments', 'fees', 'taxes']:
            if getattr(related_item, field) != getattr(instance, field):
                setattr(related_item, field, getattr(instance, field))
                saveFlag = True
        for field in ['buyerPaysSalesTax', ]:
            if getattr(related_item, field) != getattr(instance.invoice, field):
                setattr(related_item, field, getattr(instance.invoice, field))
                saveFlag = True

        if related_item.received != received_status:
            related_item.received = received_status
            related_item.paymentMethod = instance.invoice.get_payment_method()
            saveFlag = True

        if saveFlag:
            related_item.save()
            logger.info('RevenueItem associated with InvoiceItem %s updated.' % instance.id)


@receiver(post_save, sender=Invoice)
def createRevenueItemsFromInvoice(sender, instance, **kwargs):
    '''
    This signal handler exists because an invoice can be changed from
    preliminary to non-preliminary without editing the invoice items, in which
    case revenue items will need to be created.
    '''

    if 'loaddata' in sys.argv or ('raw' in kwargs and kwargs['raw']):
        return

    logger.debug('RevenueItem signal fired for Invoice %s.' % instance.id)

    if instance.status == Invoice.PaymentStatus.preliminary:
        logger.debug('Preliminary invoice. No revenue items will be created.')
        return

    for item in instance.invoiceitem_set.all():
        createRevenueItemForInvoiceItem(sender, item, **kwargs)


@receiver(post_save, sender=User)
@receiver(post_save, sender=StaffMember)
@receiver(post_save, sender=Location)
def updateTransactionParty(sender, instance, **kwargs):
    '''
    If a User, StaffMember, or Location is updated, and there exists an associated
    TransactionParty, then the name and other attributes of that party should be updated
    to reflect the new information.
    '''

    if 'loaddata' in sys.argv or ('raw' in kwargs and kwargs['raw']):
        return

    logger.debug('TransactionParty signal fired for %s %s.' % (instance.__class__.__name__, instance.id))

    party = getattr(instance, 'transactionparty', None)
    if party:
        party.save(updateBy=instance)


@receiver(get_eventregistration_data)
def reportRevenue(sender, **kwargs):

    logger.debug('Signal fired to return revenue items associated with registrations')

    regs = kwargs.pop('eventregistrations', None)
    if not regs or not isinstance(regs, QuerySet) or not (regs.model == EventRegistration):
        logger.warning('No/invalid EventRegistration queryset passed, so revenue items not found.')
        return

    extras = {}
    regs = regs.filter(invoiceItem__revenueitem__isnull=False).select_related(
        'invoiceItem__revenueitem'
    )

    for reg in regs:
        extras[reg.id] = [{
            'id': reg.invoiceItem.revenueitem.id,
            'name': reg.invoiceItem.revenueitem.description,
            'type': 'revenueitem',
            'amount': reg.invoiceItem.revenueitem.total,
        }, ]
    return extras
