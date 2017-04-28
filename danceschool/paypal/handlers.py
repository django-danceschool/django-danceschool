from django.dispatch import receiver
from django.db.models.signals import post_save
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.contrib.sites.models import Site

import requests
import six
import json
from dateutil import parser
import sys
from calendar import month_name
import logging

from danceschool.core.signals import invoice_sent, get_payment_context
from danceschool.core.models import Registration
from danceschool.core.constants import getConstant
from danceschool.financial.signals import refund_requested

from .models import Invoice

# The URLparse module was moved in Python 3, this import ensures compatibility.
if six.PY3:
    from urllib.parse import parse_qsl
else:
    from urlparse import parse_qsl


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(get_payment_context)
def getPaymentContext(sender,**kwargs):
    '''
    If using Paypal's Pay Now features, then the RegistrationSummaryView
    page needs context to provide pay now features, and well as to send invoices
    for door registrations.  This handler returns that context.
    '''
    payNowContext = {}

    reg = kwargs.get('registration',None)
    if not reg:
        return

    # Set individual item names and values for the Paypal pass-through
    itemnum = 1
    itemList = []
    itemtotals = 0

    for eventreg in reg.temporaryeventregistration_set.all():
        if eventreg.event.series:
            this_item_name = month_name[eventreg.event.month] + ' ' + str(eventreg.event.year) + ': ' + eventreg.event.series.classDescription.title[:100]
            this_item_number = 'series_%s_%s' % (eventreg.event.id,eventreg.id)
        else:
            this_item_name = _('Event: ' + eventreg.event.name)
            this_item_number = 'event_%s_%s' % (eventreg.event.id,eventreg.id)

        this_item_amount = eventreg.price

        payNowContext['item_name_' + str(itemnum)] = this_item_name
        payNowContext['item_number_' + str(itemnum)] = this_item_number
        payNowContext['amount_' + str(itemnum)] = this_item_amount

        itemList.append({
            'name': this_item_number,
            'description': this_item_name,
            'quantity': 1,
            'unitPrice': this_item_amount
        })

        itemtotals += eventreg.price
        itemnum += 1

    # This is the context that will be made available in the template.
    # Note that this context does not inlude any discount/voucher information,
    # but that information is provided in the general context data of
    # RegistrationSummaryView.
    return {
        'processor': 'Paypal',
        'custom': 'registration_%s' % reg.id,
        'invoice_id': 'registration_%s' % reg.id,
        'discount_amount_cart': max(itemtotals - reg.priceWithDiscount,0),
        'payNowItems': payNowContext,
        'invoiceItems': itemList,
        'itemTotals': itemtotals,
    }


@receiver(post_save, sender=Registration)
def addFinalRegistrationToIPN(sender,instance,**kwargs):
    # When a registration is saved (i.e. created, update the
    # IPN records to indicate the relation.)
    if 'loaddata' in sys.argv or ('raw' in kwargs and kwargs['raw']):
        return

    if instance.temporaryRegistration:
        ipn = instance.temporaryRegistration.ipnmessage_set.first()
        if ipn and not ipn.finalRegistration:
            ipn.finalRegistration = instance
            ipn.save()


@receiver(invoice_sent)
def invoice_handler(sender,**kwargs):
    """
    If the core app created an invoice, then send it to the user via Paypal.
    """
    logger.debug('Paypal invoice handler fired.')

    payerEmail = kwargs.pop('payerEmail')
    invoiceNumber = kwargs.pop('invoiceNumber')
    itemList = kwargs.pop('itemList',[])
    # amountDue = kwargs.pop('amountDue')
    discountAmount = kwargs.pop('discountAmount')

    logger.debug('Item List:')
    logger.debug(itemList)

    headers = {
        'X-PAYPAL-SECURITY-USERID': settings.PAYPAL_INVOICE_USERID,
        'X-PAYPAL-SECURITY-PASSWORD': settings.PAYPAL_INVOICE_PASSWORD,
        'X-PAYPAL-SECURITY-SIGNATURE': settings.PAYPAL_INVOICE_SIGNATURE,
        'X-PAYPAL-APPLICATION-ID': settings.PAYPAL_INVOICE_APPID,
        'X-PAYPAL-REQUEST-DATA-FORMAT': 'JSON',
        'X-PAYPAL-RESPONSE-DATA-FORMAT': 'JSON',
    }

    payload = {
        'requestEnvelope': {
            'errorLanguage': 'en_US',
        },
        'invoice': {
            'number': invoiceNumber,
            'merchantEmail': settings.PAYPAL_ACCOUNT,
            'merchantInfo': {
                'businessName': getConstant('contact__businessName'),
                'website': Site.objects.get(id=settings.SITE_ID).domain,
                'phone': getConstant('contact__businessPhone'),
                'address': {
                    'line1': getConstant('contact__businessAddress'),
                    'line2': getConstant('contact__businessAddressLineTwo'),
                    'city': getConstant('contact__businessCity'),
                    'state': getConstant('contact__businessState'),
                    'postalCode': getConstant('contact__businessZip'),
                    'countryCode': getConstant('contact__businessCountryCode'),
                },
            },
            'payerEmail': payerEmail,
            'currencyCode': getConstant('general__currencyCode'),
            'paymentTerms': 'DueOnReceipt',
            'itemList': {'item': itemList},
            'discountAmount': discountAmount,
        },
    }

    r = requests.post(
        settings.PAYPAL_INVOICE_URL,
        data=json.dumps(payload),
        headers=headers,
    )

    if (r.json()['responseEnvelope']['ack'] == 'Success'):
        logger.debug('Paypal invoice creation successful:\n%s' % r.json())

        Invoice.objects.create(
            invoiceNumber=r.json()['invoiceNumber'],
            paypalInvoiceID=r.json()['invoiceID'],
            creationDate=parser.parse(r.json()['responseEnvelope']['timestamp']),
            invoiceURL=r.json()['invoiceURL'],
            payerViewURL=r.json()['payerViewURL'],
            totalAmount=float(r.json()['totalAmount']) / 100.0,
            itemList=json.dumps(itemList),
        )

    else:
        logger.error('Paypal invoice creation failed:\n%s' % r.json())

@receiver(refund_requested)
def refund_handler(sender,**kwargs):
    """
    If the financial app processed a refund, then send it to the user via Paypal.
    """
    logger.debug('Paypal refund handler fired.')

    registration = kwargs.pop('registration')
    refundType = kwargs.pop('refundType')
    refundAmount = kwargs.pop('refundAmount')

    initial_ipn = getattr(registration,'ipnmessage',None)
    if initial_ipn:
        txnID = initial_ipn.txn_id

        # Loop through the associated Revenue items and ensure that the associated Paypal IPNCartItems
        # have refunds allocated appropriately.  Specifically, set the inital cart item's refund amount
        # to the pending refund amount (total adjustments less ones that have been allocated).
        # When the refund confirmation is received by IPN, this amount will be allocated to the new
        # IPNCartItem that is created.
        for er in registration.eventregistration_set.all():
            for ri in er.revenueitem_set.all():
                initialCartItem = ri.ipncartitem_set.first().initialCartItem
                initialCartItem.refundAmount = (-1 * ri.adjustments) + initialCartItem.allocatedAdjustment
                initialCartItem.save()

    else:
        # No matching Paypal IPN message in the system, so just fail gracefully.
        return

    payload = {
        'USER': settings.PAYPAL_REFUND_USERID,
        'PWD': settings.PAYPAL_REFUND_PASSWORD,
        'SIGNATURE': settings.PAYPAL_REFUND_SIGNATURE,
        'VERSION': 94,
        'METHOD': 'RefundTransaction',
        'TRANSACTIONID': txnID,
        'REFUNDTYPE': refundType,
    }

    if refundType == 'Partial':
        payload['AMT'] = refundAmount

    r = requests.post(
        settings.PAYPAL_REFUND_URL,
        data=payload,
    )

    response = dict(parse_qsl(r.text))

    # The IPN Handler processes the refunds, so this handler does not need to do
    # anything once the request has been sent.
    if (response['ACK'] == 'Success'):
        logger.debug('Paypal refund processed successfully:\n%s' % response)

    else:
        logger.error('Paypal invoice creation failed:\n%s' % response)
