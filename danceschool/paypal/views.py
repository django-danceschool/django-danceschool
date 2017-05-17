from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

import six
import random
from datetime import datetime
import re
from dateutil import parser
import json
import logging

from danceschool.core.helpers import emailErrorMessage
from danceschool.core.classreg import processPayment
from danceschool.core.models import TemporaryRegistration
from danceschool.vouchers.giftcertificates import processGiftCertificate
from danceschool.vouchers.models import Voucher

from .models import IPNMessage, IPNCartItem, Invoice

if six.PY3:
    from urllib.request import Request, urlopen
    from urllib.parse import urlencode

    # Ensures that checks for Unicode data types (and unicode type assignments) do not break.
    unicode = str
else:
    from urllib2 import Request, urlopen
    from urllib import urlencode


# Define logger for this file
logger = logging.getLogger(__name__)


@csrf_exempt
def payment_received(request):
    '''
    This url is called when paypal has received a payment
    '''
    logger.info('Paypal message received.')
    parameters = None
    payment_status = None

    # If turned on in settings, immediately send a debug email indicating
    if getattr(settings,'PAYPAL_DEBUG_ALL',False):
        emailErrorMessage(_("Paypal IPN debugging"),str(getattr(request,request.method)))

    # Grab the parameters from the request
    if 'payment_status' in getattr(request,request.method):
        parameters = getattr(request,request.method).copy()
        payment_status = parameters['payment_status']

    if type(payment_status) in [list,tuple]:
        payment_status = payment_status[0]

    if not (payment_status == 'Completed') and not (payment_status == 'Refunded'):
        logger.error('Paypal transaction status cannot be handled by server: %s' % payment_status)
        emailErrorMessage(_("Not Completed"),str(request.POST))
        return HttpResponse("Error.")

    # This addresses empty GET calls and the like
    if not parameters:
        logger.error('Unknown failure, returning Error.')
        return HttpResponse("Error.")

    # Paypal receives a callback from our site to verify it;
    # this prevents spoofing issues.
    logger.info('Sending callback to Paypal')
    parameters['cmd'] = '_notify-validate'

    req = Request(getattr(settings,'PAYPAL_URL',''), urlencode(parameters).encode('ascii'))
    req.add_header("Content-type", "application/x-www-form-urlencoded")
    response = urlopen(req)
    status = response.read()

    # If Python 3, returned reponse is bytes, not string, so convert to string
    # before validation.
    if type(status) is bytes:
        status = status.decode()
    logger.debug('Got response: %s' % status)
    response.close()

    if not status == "VERIFIED":
        logger.error('Status is not verified.')
        emailErrorMessage(_("Not Verified"),status)
        return HttpResponse("Error.")

    # Update parameters to address the fact that gross amounts
    # and fee amount are sometimes parsed by Python as a list
    # when we want a single number.
    parameters = dict(parameters)
    for key,value in parameters.items():
        if type(parameters[key]) is list:
            try:
                parameters[key] = float(value[0])
            except:
                parameters[key] = str(value[0])

    # Convert Paypal's passed dates to datetime objects.  The dateutil parser
    # handles time zones, unlike datetime.strptime.
    if type(parameters['payment_date']) in [str,unicode,bytes]:
        parameters['payment_date'] = parser.parse(parameters['payment_date'])

    logger.info('Ready to process IPN payment for payment status %s.' % payment_status)
    try:
        if payment_status == 'Refunded':
            processRefundedIPNPayment(parameters)
        elif payment_status == 'Completed':
            processCompletedIPNPayment(parameters)
        else:
            # This should never happen.
            raise ValueError
    except:
        logger.exception('IPN Processing failed, returning Error.')
        return HttpResponse("Error.")

    return HttpResponse('Ok')


def createIPNObjects(parameters,**kwargs):
    '''
    This function is called from both processCompletedIPNPayment
    and from processRefundedIPNPayment (i.e. every time an IPN
    transaction is to be created.  It creates the IPNPayment
    object as well as IPNCartItem related objects for this transaction.)
    '''

    logger.debug('Preparing to create IPN record.')

    # This is the list of things that should be passed when creating
    # the IPNMessage object
    ipn_object_keys = ['message','txn_id','invoice','generated_invoice','paypalInvoice','mc_currency',
                       'payer_email','payer_id','custom',
                       'payment_status','receiver_email','txn_type',
                       'mc_gross','mc_fee','payment_date','registration',
                       'finalRegistration','priorTransaction','paypalInvoice']
    ipn_object_numeric_keys = ['mc_gross','mc_fee']
    ipn_object_other_keys = ['payment_date','registration',
                             'finalRegistration','priorTransaction','paypalInvoice']

    # Fill the parameters to be passed to the IPN, with
    # the appropriate type.
    ipn_parameters = {}
    for key in ipn_object_keys:
        if key in ipn_object_numeric_keys:
            ipn_parameters[key] = parameters.pop(key,0)
        elif key in ipn_object_other_keys:
            ipn_parameters[key] = parameters.pop(key,None)
        else:
            ipn_parameters[key] = parameters.pop(key,'')

    # Anything that was passed as a kwarg takes precedence
    for key,value in kwargs.items():
        if key in ipn_object_keys:
            ipn_parameters[key] = value

    logger.debug('Writing to database, IPN parameters:\n%s' % ipn_parameters)

    ipn = IPNMessage(**ipn_parameters)
    ipn.save()
    logger.debug('IPN payment record saved.')

    # Now, parse any subitems that exist, and create records
    # for them. Get the names, numbers, and amounts for each
    # subitem by looking through the passed parameters dict.
    # If this is an invoice payment, then there will only be
    # one subitem, which is the overall invoice payment (the
    # callback doesn't include the item details from the
    # invoice.  So, for these instances, create cart item
    # records based on the JSON saved with the invoice.
    logger.debug('Remaining kwargs:\n%s' % kwargs)

    if kwargs.get('paypalInvoice') and ipn_parameters['txn_type'] == 'invoice_payment':
        itemList = json.loads(kwargs.get('paypalInvoice').itemList or '[]')

        for list_item in itemList:
            item = IPNCartItem(
                ipn=ipn,
                invoiceName=list_item['description'],
                invoiceNumber=list_item['name'],
                mc_gross=list_item['quantity'] * list_item['unitPrice'],
            )
            item.save()

        logger.debug('Finished creating cart subitem records from stored invoice details.')
    else:
        numeric_keys = []
        item_number_re = re.compile('item_number[0-9]+')

        for key in filter(item_number_re.match,parameters.keys()):
            numeric_keys.append(int(key.split('item_number')[1]))

        if numeric_keys:
            logger.debug('Creating cart subitem records.')

            for key in numeric_keys:
                item = IPNCartItem(
                    ipn=ipn,
                    invoiceName=parameters.pop('item_name%s' % key,''),
                    invoiceNumber=parameters.pop('item_number%s' % key,''),
                    mc_gross=parameters.pop('mc_gross_%s' % key,0),
                )
                # The automated refund process notes the refund amount in the initialCartItem.
                # However, the refund should actually be noted in the IPNCartItem assocated with
                # the refund transaction itself.
                if item.ipn != item.ipn.initialTransaction and item.ipn.payment_status == 'Refunded':
                    initialItem = item.initialCartItem
                    item.refundAmount = initialItem.refundAmount
                    initialItem.refundAmount = 0
                    initialItem.save()
                item.save()

            logger.debug('Finished creating cart subitem records.')

    # Return the base newly created object
    return ipn


def processCompletedIPNPayment(parameters):
    '''
    Handle IPN payment
    '''
    logger.debug('Parameters passed to process Completed payment:\n%s' % parameters)

    payment_status = parameters['payment_status']
    invoice = parameters['invoice']
    custom = parameters.get('custom','')
    txn_id = parameters['txn_id']
    txn_type = parameters['txn_type']
    mc_gross = parameters.pop('mc_gross',0)
    mc_fee = parameters.pop('mc_fee',0)
    payer_email = parameters.pop('payer_email','')

    # Fill this if this is an invoice payment.
    existingInvoice = None

    # This ensures that we record both the Paypal invoice number (for invoice payments)
    # and our invoice number.
    if txn_type == 'invoice_payment':
        invoice = parameters['invoice_number']
        parameters['generated_invoice'] = parameters['invoice']
        parameters['invoice'] = invoice

        # Update Existing invoice is this is listed as an invoice payment.  Fail gracefully
        try:
            existingInvoice = Invoice.objects.get(paypalInvoiceID=parameters['generated_invoice'])
            if not existingInvoice.paymentDate:
                existingInvoice.paymentDate = parameters['payment_date']
                existingInvoice.save()
        except:
            logger.warning('Existing Invoice not found for invoice payment.')

    certificate_id = None
    if invoice.split("_")[0] == 'giftcertificate':
        reg = None
        certificate_id = invoice.split("_")[1]
        recipient_name = custom
    else:
        regId = int(invoice.split("_")[1])
        reg = TemporaryRegistration.objects.filter(id=regId)[0]

    # check to see if txn_id has already been encountered
    # if it has, don't go on
    if IPNMessage.objects.filter(txn_id=txn_id).count() > 0:
        logger.warning('This transaction has already been encountered; aborting process.')
        return

    # Create the database objects for this transaction
    createIPNObjects(parameters,registration=reg,
                     paypalInvoice=existingInvoice,
                     mc_gross=mc_gross, mc_fee=mc_fee,
                     payer_email=payer_email)

    # If this is a payment for a registration, return
    # to the core app to make a real registration object
    # and send a confirmation email. If this is a payment
    # for a gift certificate, proceed to the vouchers app
    # to make the voucher and send the confirmation email.
    if certificate_id:
        logger.info('Processing gift certificate from id %s to recipient %s' % (certificate_id,recipient_name))
        processGiftCertificate(mc_gross,payer_email,payment_status,txn_id,recipient_name=recipient_name)
    elif reg:
        logger.info('Processing payment for TemporaryRegistration with id=%s' % reg.id)
        processPayment(mc_gross,mc_fee,payment_status,reg,invoiceNumber=txn_id)
    else:
        # Unknown payment received
        logger.error('Unknown payment invoice received; aborting.')
        emailErrorMessage(_("Unknown payment invoice received"),invoice)


def testProcessCompletedIPNPayment(invoice_id,total,email):
    '''
    This function exists for testing purposes only and can
    be called to ensure that the payment processing
    functionality is working.
    '''
    parameters = {
        'txn_id': "txn_" + str(random.randint(0,1e12)),
        'invoice': invoice_id,
        'mc_currency': 0.0,
        'mc_gross': total,
        'mc_fee': 1.0,
        'payer_email': email,
        'payer_id': 0,
        'custom': "",
        'payment_status': "Completed",
        'payment_date': datetime.now(),
        'receiver_email': email,
        'txn_type': "",
    }
    processCompletedIPNPayment(parameters)


def processRefundedIPNPayment(parameters):
    '''
    Process refund transactions.
    '''
    invoice = parameters['invoice']
    mc_gross = parameters.get('mc_gross',0)
    txn_id = parameters['txn_id']
    payment_date = parameters['payment_date']

    old_ipn = IPNMessage.objects.filter(**{'invoice':invoice,'priorTransaction':None}).first()
    if not old_ipn:
        logger.error('Unexpected refund received.')
        emailErrorMessage(_('Unexpected refund received'),invoice)
        return

    # Now, create the new IPN objects for this transaction.
    ipn = createIPNObjects(parameters,mc_gross=mc_gross,
                           priorTransaction=old_ipn)

    # For both gift certificates and class registrations, update
    # the IPN record to reflect either a total or a partial refund
    if ipn.netRevenue == 0:
        logger.debug('Transaction is full refund. Processing.')
        old_ipn.message = '\n'.join([
            old_ipn.message,
            _('REFUNDED: %s, %s on %s.' % (txn_id,-1 * mc_gross,payment_date))
        ]).strip(" ")
        old_ipn.save()
        # If there's a matching registration object, mark all of
        # the affiliated eventregistration objects as cancelled, too.
        if old_ipn.finalRegistration:
            for eventreg in old_ipn.finalRegistration.eventregistration_set.all():
                eventreg.cancelled = True
                eventreg.save()
    else:
        logger.debug('Transaction is partial refund. Processing.')
        old_ipn.message = '\n'.join([
            old_ipn.message,
            _('PARTIAL REFUND: %s, %s on %s.' % (txn_id,-1 * mc_gross,payment_date))
        ]).strip(" ")
        old_ipn.save()

    # If this is a gift certificate, reduce the amount available
    # by the amount of the refund.
    if invoice.split("_")[0] == 'giftcertificate':
        logger.debug('Attempting to locate previous gift certificate voucher.')
        old_voucher = Voucher.objects.filter(voucherId='GC_' + str(old_ipn.txn_id)).first()
        if not old_voucher:
            logger.error('Gift certificate refund received but associated voucher not found.')
            emailErrorMessage(_('Refund received but associated voucher not found.'),txn_id)
        else:
            logger.debug('Reducing voucher value by increasing refundAmount.')
            old_voucher.refundAmount = old_voucher.refundAmount + -1 * mc_gross
            old_voucher.save()
            if old_voucher.amountLeft < 0:
                emailErrorMessage(_('Refund received on gift certificate is too large.'),txn_id)
            logger.info('Completed voucher processing.')
