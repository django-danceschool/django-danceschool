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

from .models import ExpensePurpose, RevenueItem, RepeatedExpenseRule, TransactionParty


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(post_save, sender=EventStaffMember)
@receiver(m2m_changed, sender=EventStaffMember.occurrences.through)
def modifyExistingExpenseItemsForEventStaff(sender, instance, **kwargs):

    if 'loaddata' in sys.argv or ('raw' in kwargs and kwargs['raw']):
        return

    changed = False
    for prop in ['category', 'staffMember', 'replacedStaffMember', 'specifiedHours']:
        if getattr(instance, prop, None) != getattr(instance, f'__original_{prop}', None):
            changed = True
    if not (kwargs.get('action', None) in ['post_add', 'post_remove'] or changed == True):
        return

    logger.debug('ExpenseItem signal fired for EventStaffMember %s.' % instance.pk)

    new_payTo, created = TransactionParty.objects.get_or_create(
        staffMember=instance.staffMember,
        defaults={'name': getattr(instance.staffMember, 'fullName', '')}
    )

    pref = getConstant('financial__autoGenerateExpensesEventStaff')
    action = kwargs.get('action')

    if pref == 'per_occurrence':
        # Per-occurrence mode: each ExpensePurpose has an occurrence FK.

        # Step 1: Delete unpaid items for occurrences removed from the staffer.
        if action == 'post_remove':
            pk_set = kwargs.get('pk_set') or set()
            for purpose in instance.related_expenses.filter(occurrence__pk__in=pk_set):
                if not purpose.item.paid:
                    purpose.item.delete()

        # Step 2: Redistribute hours across all remaining per-occurrence items.
        allocation = instance.allocationByOccurrence
        purposes = instance.related_expenses.filter(
            occurrence__isnull=False
        ).select_related('item', 'item__expenseRule', 'occurrence')

        if purposes.exists():
            logger.debug('Updating per-occurrence expense items for event staff member.')
            for purpose in purposes:
                expense = purpose.item
                if getattr(
                    expense.expenseRule, 'applyRateRule', None
                ) != RepeatedExpenseRule.RateRuleChoices.hourly:
                    continue
                occ = purpose.occurrence
                occ_hours = (
                    allocation.get((occ.id, instance.event.id), {}).get('duration', 0) / 3600
                )
                expense.hours = occ_hours
                expense.total = occ_hours * expense.wageRate
                expense.approved = None
                if not expense.paid:
                    logger.debug('Updating expense item %s.' % expense.id)
                    expense.description = expense.description.replace(
                        expense.payTo.name, getattr(instance.staffMember, 'fullName', '')
                    )
                    expense.payTo = new_payTo
                    expense.save()

        # Also handle the replaced staff member.
        if hasattr(instance.replacedStaffMember, 'staffMember'):
            logger.debug('Adjusting per-occurrence totals for replaced event staff member.')
            replaced = instance.replacedStaffMember
            replaced_allocation = replaced.allocationByOccurrence
            for purpose in replaced.related_expenses.filter(
                occurrence__isnull=False
            ).select_related('item', 'item__expenseRule', 'occurrence'):
                expense = purpose.item
                if getattr(
                    expense.expenseRule, 'applyRateRule', None
                ) != RepeatedExpenseRule.RateRuleChoices.hourly:
                    continue
                occ = purpose.occurrence
                occ_hours = (
                    replaced_allocation.get((occ.id, replaced.event.id), {}).get('duration', 0) / 3600
                )
                expense.hours = occ_hours
                expense.total = occ_hours * expense.wageRate
                expense.approved = None
                if not expense.paid:
                    logger.debug('Updating expense item %s' % expense.id)
                    expense.save()

    else:
        # Per-event mode (default): one ExpenseItem per EventStaffMember.
        staff_expenses = [x.item for x in instance.related_expenses.all()]

        if staff_expenses:
            logger.debug('Updating existing expense item for event staff member.')
            # Fill in the updated hours and the updated total.  Set the expense item
            # to unapproved.
            for expense in staff_expenses:

                if getattr(
                    expense.expenseRule, 'applyRateRule', None
                ) == RepeatedExpenseRule.RateRuleChoices.hourly:
                    expense.hours = instance.netHours
                    expense.total = expense.hours * expense.wageRate
                    expense.approved = None

                # Update who the expense should be paid to if the identity of the
                # staff member has changed and the expense is not already paid.
                if not expense.paid:
                    logger.debug('Updating expense item %s.' % expense.id)

                    expense.description = expense.description.replace(
                        expense.payTo.name, getattr(instance.staffMember, 'fullName', '')
                    )
                    expense.payTo = new_payTo
                    expense.save()

        if hasattr(instance.replacedStaffMember, 'staffMember'):
            logger.debug('Adjusting totals for replaced event staff member.')

            replaced_expenses = [
                x.item for x in instance.replacedStaffMember.related_expenses.all() if
                getattr(
                    x.item.expenseRule, 'applyRateRule', None
                ) == RepeatedExpenseRule.RateRuleChoices.hourly
            ]

            # Fill in the updated hours and the updated total.  Set the expense item
            # to unapproved.
            for expense in replaced_expenses:
                expense.hours = instance.replacedStaffMember.netHours
                expense.total = expense.hours * expense.wageRate
                expense.approved = None

                if not expense.paid:
                    logger.debug('Updating expense item %s' % expense.id)
                    expense.save()


@receiver(post_save, sender=EventOccurrence)
def modifyExistingExpenseItemsForSeriesClass(sender, instance, **kwargs):
    if 'loaddata' in sys.argv or ('raw' in kwargs and kwargs['raw']):
        return

    logger.debug('ExpenseItem signal fired for EventOccurrence %s.' % instance.id)

    pref = getConstant('financial__autoGenerateExpensesEventStaff')

    if pref == 'per_occurrence':
        # Per-occurrence mode: update expense items for all event staff, but
        # only those items that are linked to individual occurrences. When one
        # occurrence changes, the proportional allocation shifts for all
        # occurrences in the event, so we recalculate the whole event.
        event_staff = EventStaffMember.objects.filter(
            Q(event=instance.event) &
            Q(related_expenses__item__expenseRule__applyRateRule=RepeatedExpenseRule.RateRuleChoices.hourly) &
            Q(related_expenses__occurrence__isnull=False)
        ).distinct().prefetch_related(
            'related_expenses__occurrence',
            'related_expenses__item',
            'related_expenses__item__expenseRule',
            'occurrences',
        )

        for staffer in event_staff:
            allocation = staffer.allocationByOccurrence
            for purpose in staffer.related_expenses.filter(occurrence__isnull=False):
                expense = purpose.item
                if getattr(
                    expense.expenseRule, 'applyRateRule', None
                ) != RepeatedExpenseRule.RateRuleChoices.hourly:
                    continue
                occ = purpose.occurrence
                occ_hours = (
                    allocation.get((occ.id, staffer.event.id), {}).get('duration', 0) / 3600
                )
                expense.hours = occ_hours
                expense.total = occ_hours * expense.wageRate
                expense.approved = None
                expense.save()

    else:
        # Per-event mode: recalculate total hours across all occurrences and
        # update the single expense item per EventStaffMember.
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

    reg_ids = kwargs.pop('eventregistrations', [])

    extras = {}
    regs = EventRegistration.objects.filter(
        id__in=reg_ids
    ).filter(
        invoiceItem__revenueitem__isnull=False
    ).select_related(
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
