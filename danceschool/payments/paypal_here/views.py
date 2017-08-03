from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.utils.functional import SimpleLazyObject

import six
import logging
import json

from danceschool.core.models import TemporaryRegistration, Invoice
from danceschool.core.constants import getConstant

from .models import PaypalHereRecord

if six.PY3:
    # Ensures that checks for Unicode data types (and unicode type assignments) do not break.
    unicode = str


# Define logger for this file
logger = logging.getLogger(__name__)


def createPaypalHerePayment(request):
    '''
    This view handles the creation of Paypal Here Payment objects for point-of-sale integration.

    All Paypal Here payments must either be associated with a pre-existing Invoice
    or a registration, or they must have an amount and type passed in the post data
    (such as gift certificate payment requests).
    '''
    logger.info('Received request for Paypal Here payment.')

    invoice_id = request.POST.get('invoice_id')
    tr_id = request.POST.get('reg_id')
    amount = request.POST.get('amount')
    submissionUserId = request.POST.get('user_id')
    transactionType = request.POST.get('transaction_type')
    taxable = request.POST.get('taxable', False)

    # If a specific amount to pay has been passed, then allow payment
    # of that amount.
    if amount:
        try:
            amount = float(amount)
        except ValueError:
            logger.error('Invalid amount passed')
            return HttpResponseBadRequest()

    # Parse if a specific submission user is indicated
    submissionUser = None
    if submissionUserId:
        try:
            submissionUser = User.objects.get(id=int(submissionUserId))
        except (ValueError, ObjectDoesNotExist):
            logger.warning('Invalid user passed, submissionUser will not be recorded.')

    try:
        # Invoice transactions are usually payment on an existing invoice.
        if invoice_id:
            this_invoice = Invoice.objects.get(id=invoice_id)
            this_description = _('Invoice Payment: %s' % this_invoice.id)
            if not amount:
                amount = this_invoice.outstandingBalance
        # This is typical of payment at the time of registration
        elif tr_id:
            tr = TemporaryRegistration.objects.get(id=int(tr_id))
            this_invoice = Invoice.get_or_create_from_registration(tr, submissionUser=submissionUser)
            this_description = _('Registration Payment: #%s' % tr_id)
            if not amount:
                amount = this_invoice.outstandingBalance
        # All other transactions require both a transaction type and an amount to be specified
        elif not transactionType or not amount:
            logger.error('Insufficient information passed to createPaypalHerePayment view.')
            raise ValueError
        else:
            # Gift certificates automatically get a nicer invoice description
            if transactionType == 'Gift Certificate':
                this_description = _('Gift Certificate Purchase')
            else:
                this_description = transactionType
            this_invoice = Invoice.create_from_item(
                float(amount),
                this_description,
                submissionUser=submissionUser,
                calculate_taxes=(taxable is not False),
                transactionType=transactionType,
            )
    except (ValueError, ObjectDoesNotExist) as e:
        logger.error('Invalid registration information passed to createPaypalHerePayment view: (%s, %s, %s)' % (invoice_id, tr_id, amount))
        logger.error(e)
        return HttpResponseBadRequest()

    this_total = min(this_invoice.outstandingBalance, amount)

    # Paypal requires the Payment request to include redirect URLs.  Since
    # the plugin can handle actual redirects, we just pass the base URL for
    # the current site.
    site = SimpleLazyObject(lambda: get_current_site(request))
    protocol = 'https' if request.is_secure() else 'http'
    base_url = SimpleLazyObject(lambda: "{0}://{1}".format(protocol, site.domain))

    passed_info = {
        'accepted': 'card,paypal',
        'step': 'choosePayment',
        'returnUrl': str(base_url) + reverse('executePaypalHerePayment') + '?result={result}&Type={Type}&InvoiceId={InvoiceId}&Number={Number}&Email={Email}&TxId={TxId}&GrandTotal={GrandTotal}',
    }

    passed_invoice_info = {
        'paymentTerms': 'DueOnReceipt',
        'businessName': getConstant('contact__businessName'),
        'currencyCode': getConstant('general__currencyCode'),
        'taxInclusive': (not getConstant('registration__buyerPaysSalesTax')),
        'number': str(this_invoice.id),
        'description': str(this_description),
        'itemList': {
            'item': [
            ],
        }
    }

    # Pre-fill the email address field if possible
    if this_invoice.temporaryRegistration:
        passed_invoice_info['payerEmail'] = this_invoice.temporaryRegistration.email

    for item in this_invoice.invoiceitem_set.all():
        passed_invoice_info['itemList']['item'].append({
            'name': str(item.name),
            'unitPrice': item.grossTotal,
            'quantity': 1,
            'taxName': 'Tax',
            'taxRate': getConstant('registration__salesTaxRate') if item.taxes > 0 else 0,
        })

    # This ensures that the amount that is being paid matches the
    # amount that will be billed in the app.
    passed_invoice_info['discountAmount'] = \
        sum([x.get('unitPrice') for x in passed_invoice_info['itemList']['item']]) \
        - this_total

    # Using this instead of urllib because Paypal Here is wonky about encoding escape characters
    passed_info['invoice'] = json.dumps(passed_invoice_info).replace('#','%23')
    redirect_url = 'paypalhere://takePayment?accepted=%s&step=%s&returnUrl=%s&invoice=%s' % \
        (passed_info['accepted'], passed_info['step'], passed_info['returnUrl'], passed_info['invoice'])

    logger.info('Returning URL for Paypal Here redirect.')

    return JsonResponse({
        'created': True,
        'invoiceNumber': this_invoice.id,
        'redirectUrl': redirect_url,
    })


def executePaypalHerePayment(request):
    '''
    Once a Paypal Here payment has been processed, the individual should be returned
    here for processing.  This just captures the response data and sends them to the
    success page.
    '''

    executedType = request.GET.get('Type')
    paypalInvoiceId = request.GET.get('InvoiceId')
    invoiceId = request.GET.get('Number')
    payerEmail = request.GET.get('Email')
    txId = request.GET.get('TxId')
    grandTotal = float(request.GET.get('grandTotal', 0))

    # If the transaction did not complete, type will be UNKNOWN
    if executedType.lower() == 'unknown':
        logger.warning('Paypal Here transaction was not completed; invoice remains unpaid.')
        return HttpResponseBadRequest()

    # Find the invoice against which this payment was made
    try:
        this_invoice = Invoice.objects.get(id=invoiceId)
    except ObjectDoesNotExist:
        logger.error('Invalid Invoice ID passed: %s' % invoiceId)
        return HttpResponseBadRequest()

    PaypalHereRecord.objects.create(
        invoice=this_invoice,
        paymentType=executedType,
        paypalInvoiceId=paypalInvoiceId,
        payerEmail=payerEmail,
        txId=txId,
        total=grandTotal,
    )

    this_invoice.processPayment(
        amount=grandTotal,
        paidOnline=True,
        methodName='Paypal Here',
        methodTxn=paypalInvoiceId,
        notify=payerEmail,
    )

    return HttpResponseRedirect(reverse('registration'))
