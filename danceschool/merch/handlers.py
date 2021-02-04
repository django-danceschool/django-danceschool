from django.utils.translation import gettext_lazy as _
from django.dispatch import receiver
from django.core.exceptions import ObjectDoesNotExist

from collections import Counter
import logging

from danceschool.core.signals import (
    process_cart_items, invoice_finalized, invoice_cancelled
)
from danceschool.core.models import Invoice

from .models import MerchItemVariant, MerchOrder, MerchOrderItem


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(process_cart_items)
def processMerch(sender, **kwargs):
    '''
    Take the items data that comes from the door registration page (in regData).
    Create an order if necessary, or update the existing order.  Return a
    dictionary that will go back into regData (basically the same dictionary but
    adding the reference to the order).
    '''
    
    errors = []
    items_data = [
        x for x in kwargs.pop('items_data', [])
        if x.get('itemType', None) == 'merch'
    ]
    orders_data = kwargs.pop('orders_data', {})

    if 'merch' not in orders_data.keys() or not items_data:
        return
    order_number = orders_data.get('merch', None)

    # Access the existing merchandise order, or create a new one.
    if order_number:
        try:
            merch_order = MerchOrder.objects.get(id=order_number)
        except [ObjectDoesNotExist, ValueError]:
            errors.append({
                'code': 'invalid_order_id',
                'message': _('Invalid order ID passed.')
            })
    else:
        merch_order = MerchOrder(
            status=MerchOrder.OrderStatus.unsubmitted
        )

    variant_ids = [x.get('variantId') for x in items_data if x.get('variantId')]
    variant_counter = Counter(variant_ids)
    variants = MerchItemVariant.objects.filter(id__in=variant_ids)

    # Check for whether individual item variants show up more than once.  If so,
    # consolidate any items that are not already associated with a MerchOrderItem
    # record by adding up quantities.
    for variantId, count in variant_counter.items():
        if variantId not in variants.values_list('id', flat=True):
            errors.append({
                'code': 'invalid_variant_id',
                'message': _('Invalid variant ID passed.')
            })
            continue
        if count > 1:
            other_items = [x for x in items_data if x.get('variantId') != variantId]
            these_items = [x for x in items_data if x.get('variantId') == variantId]
            these_items = sorted(these_items, key = lambda i: i.get('orderItem') or 0, reverse=True)
            these_items[0]['quantity'] = sum([x.get('quantity', 0) for x in these_items])
            items_data = other_items + [these_items[0]]

    unmatched_order_item_ids = merch_order.items.values_list('id', flat=True)
    new_order_items = []
    new_items_data = []

    for item in items_data:
            # The existing order item should be found if its ID is passed.
            # Otherwise, create a new order item
            if item.get('orderItem', None):
                try:
                    this_order_item = merch_order.items.get(id=item.get('orderItem'),item__id=item.get('variantId'))
                    logger.debug('Found existing merch order item: {}'.format(this_order_item.id))
                    this_order_item.quantity = item.get('quantity')
                    new_order_items.append(this_order_item)
                    unmatched_order_item_ids.remove(this_order_item.id)
                except [ObjectDoesNotExist, ValueError]:
                    errors.append({
                        'code': 'invalid_order_item_id',
                        'message': _('Invalid order item ID passed.')
                    })
                    continue
            else:
                # Check that the quantity requested of the item is not greater
                # than the currently available quantity.
                this_variant = MerchItemVariant.objects.get(id=item.get('variantId'))

                logger.debug('Creating merch order item for merch variant: {}'.format(this_variant.sku))
                new_order_items.append(MerchOrderItem(
                    order=merch_order,
                    item=this_variant,
                    quantity=item.get('quantity', 0)
                ))

    # Update the database
    # TODO: I think that the dictionary still needs a bunch of new fields here
    for new_item in new_order_items:
        new_item.save()
        new_items_data.append({
            'itemType': 'merch',
            'orderItem': new_item.id,
            'variantId': new_item.item.id,
            'quantity': new_item.quantity,
        })
        
    print(new_items_data)
    return new_items_data


@receiver(invoice_finalized)
def processFinalizedInvoice(sender, **kwargs):
    '''
    When an invoice is finalized because a payment has been made, any
    order items associated with that invoice may need to have their status
    updated in order to indicate that they are ready to be fulfilled.
    '''
    invoice = kwargs.pop('invoice', None)
    
    if not invoice or not isinstance(invoice, Invoice):
        logger.error('invoice_finalized signal fired without passing a valid invoice.')
        return

    order = getattr(invoice, 'merchOrder', None)

    if not order:
        logger.debug('Invoice {} does not have an associated merchandise order'.format(invoice.id))
        return

    if order.status in [order.OrderStatus.cancelled, order.OrderStatus.fullRefund]:
        logger.warning(
            (
                'Invoice {} is being finalized but the associated merch order ' +
                'has been cancelled/refunded.'
            ).format(invoice.id)
        )
    elif order.status == order.OrderStatus.unsubmitted:
        order.status = order.OrderStatus.submitted
        order.save()


@receiver(invoice_cancelled)
def processCancelledInvoice(sender, **kwargs):
    '''
    When an invoice is finalized because a payment has been made, any
    order items associated with that invoice may need to have their status
    updated in order to indicate that they are ready to be fulfilled.
    '''
    invoice = kwargs.pop('invoice', None)
    
    if not invoice or not isinstance(invoice, Invoice):
        logger.error('invoice_finalized signal fired without passing a valid invoice.')
        return

    order = getattr(invoice, 'merchOrder', None)

    if not order:
        logger.debug('Invoice {} does not have an associated merchandise order'.format(invoice.id))
        return

    if invoice.status == invoice.PaymentStatus.cancelled:
        order.status = order.OrderStatus.cancelled
    elif invoice.status == invoice.PaymentStatus.fullRefund:
        order.status = order.OrderStatus.fullRefund
    order.save()
