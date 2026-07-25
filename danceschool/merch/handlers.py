from django.utils.translation import gettext_lazy as _
from django.db.models import Prefetch
from django.dispatch import receiver
from django.core.exceptions import ObjectDoesNotExist

from collections import Counter
import logging

from danceschool.core.signals import (
    invoice_finalized, invoice_cancelled,
    get_invoice_related, get_invoice_item_related,
    get_cart_invoice_related, get_cart_invoice_item_related
)
from danceschool.core.models import Invoice, InvoiceItem
from danceschool.core.signals import collect_purchasable_items

from .models import MerchItem, MerchItemVariant, MerchOrder, MerchOrderItem
from .serializers import MerchItemSerializer


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(collect_purchasable_items)
def merchitem_purchasables(sender, **kwargs):
    ''' Return eligible merchandise for purchase at the door only. '''
    if not kwargs.get('payAtDoor', False):
        return
    qs = (
        MerchItem.objects.prefetch_related(
            Prefetch(
                'item_variant',
                queryset=MerchItemVariant.objects.filter(soldOut=False)
            )
        )
    )
    return (qs, MerchItemSerializer)


@receiver(get_invoice_related, dispatch_uid='linkMerchOrder')
def linkMerchOrder(sender, **kwargs):
    '''
    This method checks to see whether a MerchOrder is needed for this
    transaction, and whether one already exists.  It returns a MerchOrder.
    '''

    invoice = kwargs.get('invoice')
    post_data = kwargs.get('post_data', {})

    if not isinstance(invoice, Invoice):
        return {
            'status': 'error',
            'errors': [{
                'code': 'no_invoice_passed',
                'message': _('No invoice passed to get_invoice_related signal handler.')
            }]
        }

    merchorder_items = [x for x in post_data.get('items', []) if x.get('type', None) == 'merchItem']
    if not merchorder_items:
        return {}

    response = {
        '__related_merchitemvariants': MerchItemVariant.objects.filter(
            id__in=[x.get('variantId') for x in merchorder_items if x.get('variantId', None)]
        ),
    }

    try:
        order = MerchOrder.objects.get(invoice=invoice)
    except ObjectDoesNotExist:
        order = MerchOrder(invoice=invoice, status=MerchOrder.OrderStatus.unsubmitted)

    if not order.itemsEditable:
        return {
            'status': 'error',
            'errors': [{
                'code': 'merchorder_not_editable',
                'message': _('This invoice is linked to a merchandise order that is no longer editable.'),
            }],
        }

    response.update({'__relateditem_merchorder': order})
    return {'status': 'success', 'response': response}


@receiver(get_cart_invoice_related, dispatch_uid='linkCartMerchOrder')
def linkCartMerchOrder(sender, **kwargs):
    '''
    This method checks to see whether a MerchOrder is needed for this
    transaction, and whether one already exists.  It returns a MerchOrder.
    '''

    invoice = kwargs.get('invoice')
    item_data = kwargs.get('item_data', {})

    if not isinstance(invoice, Invoice):
        return {
            'status': 'error',
            'errors': [{
                'code': 'no_invoice_passed',
                'message': _('No invoice passed to get_invoice_related signal handler.')
            }]
        }

    merchorder_items = [x for x in item_data if x.get('item_type', None) == 'MerchItem']
    if not merchorder_items:
        return {}

    response = {
        '__related_merchitemvariants': MerchItemVariant.objects.filter(
            id__in=[x.get('variant_id') for x in merchorder_items if x.get('variant_id', None)]
        ),
    }

    try:
        order = MerchOrder.objects.get(invoice=invoice)
    except ObjectDoesNotExist:
        order = MerchOrder(invoice=invoice, status=MerchOrder.OrderStatus.unsubmitted)

    if not order.itemsEditable:
        return {
            'status': 'error',
            'errors': [{
                'code': 'merchorder_not_editable',
                'message': _('This invoice is linked to a merchandise order that is no longer editable.'),
            }],
        }

    response.update({'__relateditem_merchorder': order})
    return {'status': 'success', 'response': response}


@receiver(get_invoice_item_related)
def linkMerchOrderItems(sender, **kwargs):
    '''
    Link individual merchandise order items to invoice items.
    '''

    item = kwargs.get('item')
    item_data = kwargs.get('item_data', {})
    post_data = kwargs.get('post_data', {})
    prior_response = kwargs.get('prior_response', {})

    if not item_data.get('type', None) == 'merchItem':
        return {}

    errors = []
    response = {'type': 'merchItem'}

    if not isinstance(item, InvoiceItem):
        errors.append({
            'code': 'no_invoiceitem_passed',
            'message': _('No invoice item passed to get_invoice_item_related signal handler.')
        })

    order = prior_response.get('__relateditem_merchorder')
    item_variants = prior_response.get(
        '__related_merchitemvariants',
        MerchItemVariant.objects.none()
    )

    if not order:
        errors.append({
            'code': 'no_merchorder',
            'message': _('No merchandise order passed to link order items to.'),
        })

    try:
        this_item_variant = item_variants.get(id=item_data.get('variantId', None))
        response.update({
            'variantId': this_item_variant.id,
            'description': this_item_variant.fullName,
        })
    except ObjectDoesNotExist:
        errors.append({
            'code': 'invalid_item_variant_id',
            'message': _('Invalid merchandise item variant ID passed.'),
        })
        this_item_variant = None

    if not getattr(order, 'itemsEditable', False):
        errors.append({
            'code': 'merchorder_not_editable',
            'message': _('This invoice is linked to a merchandise order that is no longer editable.'),
        })

    if errors:
        return {'status': 'failure', 'errors': errors}

    # Check the other items in POST data to ensure
    # that this is the only one for this item variant..
    same_item_variant = [
        x for x in post_data.get('items',[]) if
        x.get('type') == 'merchItem' and
        x.get('variantId') == this_item_variant.id
    ]

    if len(same_item_variant) > 1:
        errors.append({
            'code': 'duplicate_item_variant',
            'message': _(
                (
                    'You cannot add {variant_name} to the same ' +
                    'order multiple times. Adjust the quantity instead.'
                ).format(variant_name=this_item_variant.fullName)
            )
        })

    # Since there are no errors, we can proceed to find an existing
    # MerchOrderItem or to create a new one.
    created_order_item = False

    this_order_item = MerchOrderItem.objects.filter(invoiceItem__id=item.id).first()

    if not this_order_item:
        logger.debug('Creating merch order item for invoice item {}.'.format(item.id))
        this_order_item = MerchOrderItem(
            order=order,
            invoiceItem=item,
            item=this_item_variant,
        )
        created_order_item = True

    if this_order_item.item != this_item_variant:
        errors.append({
            'code': 'merchandise_mismatch',
            'message': _('Existing merchandise order item is for a different item of merchandise.'),
        })
    if this_order_item.order != order:
        errors.append({
            'code': 'order_mismatch',
            'message': _('Existing merchandise order item is associated with a different merchandise order.'),
        })

    if errors:
        return {'status': 'error', 'errors': errors}

    # Update quantity and pricing.
    old_quantity = this_order_item.quantity
    this_order_item.quantity = item_data.get('quantity', 1)
    response['quantity'] = this_order_item.quantity

    item.grossTotal = this_order_item.grossTotal
    item.total = item.grossTotal
    item.taxRate = this_order_item.item.item.salesTaxRate
    item.calculateTaxes()
    item.description = this_item_variant.fullName

    if (created_order_item and this_order_item.item.soldOut):
        errors.append({
            'code': 'sold_out',
            'message': _('Item "{}" is sold out.'.format(this_order_item.item))
        })
    elif (
        (created_order_item or this_order_item.quantity != old_quantity) and
        this_order_item.item.currentInventory < this_order_item.quantity
    ):
        errors.append({
            'code': 'insufficient_inventory',
            'message': _('Item "{}" does not have {} units available.'.format(
                this_order_item.item, this_order_item.quantity
            ))
        })

    # Handle auto-submit behavior.  If all items have autoFufill == True then
    # the order will be automatically marked as fulfilled when the invoice is
    # finalized.
    response['autoFulfill'] = item_data.get('autoFulfill', None)
    if (
        item_data.get('autoFulfill', False) is True and
        order.data.get('__autoFulfill', None) in [None, True]
    ):
        order.data['__autoFulfill'] = True
    else:
        order.data['__autoFulfill'] = False

    # Now that all checks are complete, return failure or success.
    if errors:
        return {'status': 'failure', 'errors': errors}

    response['__relateditem_merchorderitem'] = this_order_item
    return {'status': 'success', 'response': response}


@receiver(get_cart_invoice_item_related, dispatch_uid='linkCartMerchOrderItems')
def linkCartMerchOrderItems(sender, **kwargs):
    '''
    For each merchandise item in the cart, creates a MerchOrderItem linked to
    the InvoiceItem. Looks up the variant by SKU, checks inventory, and sets
    pricing on the invoice item.
    '''
    item = kwargs.get('item')
    item_data = kwargs.get('item_data', {})
    cart_data = kwargs.get('cart_data', [])
    prior_response = kwargs.get('prior_response', {})
    purchasable_registry = kwargs.get('purchasable_registry', [])

    sku = item_data.get('sku', '')
    item_id = item_data.get('item_id')

    if item_data.get('item_type') != 'MerchItem':
        return {}

    # Identify whether this is a merch item via the purchasable registry.
    # This avoids any reliance on SKU format conventions.
    this_merch_item = None
    for qs, _serializer in purchasable_registry:
        if qs.model == MerchItem:
            try:
                this_merch_item = qs.get(id=item_id)
            except ObjectDoesNotExist:
                pass
            break  # Only one MerchItem queryset expected; stop after checking it.

    if this_merch_item is None:
        return {}  # Not a merch item.

    if not isinstance(item, InvoiceItem):
        return {
            'status': 'error',
            'errors': [{'code': 'no_invoiceitem_passed', 'message': _('No invoice item passed to get_cart_invoice_item_related signal handler.')}]
        }

    order = prior_response.get('__relateditem_merchorder')
    if not order:
        return {
            'status': 'error',
            'errors': [{'code': 'no_merchorder', 'message': _('No merchandise order found for this cart.')}]
        }

    if not order.itemsEditable:
        return {
            'status': 'error',
            'errors': [{'code': 'merchorder_not_editable', 'message': _('This invoice is linked to a merchandise order that is no longer editable.')}]
        }

    # Look up the variant by SKU, scoped to the confirmed merch item.
    try:
        this_item_variant = MerchItemVariant.objects.get(sku=sku, item=this_merch_item)
    except ObjectDoesNotExist:
        return {
            'status': 'error',
            'errors': [{'code': 'invalid_variant_sku', 'message': _('Invalid merchandise variant SKU.')}]
        }

    errors = []
    response = {'variantId': this_item_variant.id, 'description': this_item_variant.fullName}

    # Check for duplicate variant in the same cart.
    same_variant = [x for x in cart_data if x.get('sku') == sku and x.get('item_id') == item_id]
    if len(same_variant) > 1:
        errors.append({
            'code': 'duplicate_item_variant',
            'message': _(
                'You cannot add {variant_name} to the same order multiple times. '
                'Adjust the quantity instead.'
            ).format(variant_name=this_item_variant.fullName)
        })

    if errors:
        return {'status': 'error', 'errors': errors}

    # Since create_invoice_from_cart() deletes all existing invoice items before
    # the loop, always create a fresh MerchOrderItem.
    this_order_item = MerchOrderItem(order=order, invoiceItem=item, item=this_item_variant)
    this_order_item.quantity = item_data.get('quantity', 1)
    response['quantity'] = this_order_item.quantity

    item.grossTotal = this_order_item.grossTotal
    item.total = item.grossTotal
    item.taxRate = this_order_item.item.item.salesTaxRate
    item.calculateTaxes()
    item.description = this_item_variant.fullName

    # Check inventory.
    if this_order_item.item.soldOut:
        errors.append({
            'code': 'sold_out',
            'message': _('Item "{}" is sold out.'.format(this_order_item.item))
        })
    elif this_order_item.item.currentInventory < this_order_item.quantity:
        errors.append({
            'code': 'insufficient_inventory',
            'message': _('Item "{}" does not have {} units available.'.format(
                this_order_item.item, this_order_item.quantity
            ))
        })

    # Handle auto-fulfill: if all items set autoFulfill=True, the order is
    # automatically marked fulfilled when the invoice is finalized.
    response['autoFulfill'] = item_data.get('autoFulfill', None)
    if (
        item_data.get('autoFulfill', False) is True and
        order.data.get('__autoFulfill', None) in [None, True]
    ):
        order.data['__autoFulfill'] = True
    else:
        order.data['__autoFulfill'] = False

    if errors:
        return {'status': 'failure', 'errors': errors}

    response['__relateditem_merchorderitem'] = this_order_item
    return {'status': 'success', 'response': response}


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
        autoFulfill = order.data.pop('__autoFulfill', False)
        if autoFulfill:
            order.status = order.OrderStatus.fulfilled
        else:
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
    order.save(updateInvoice=False)
