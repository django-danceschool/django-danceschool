from django.http import JsonResponse, HttpResponseBadRequest
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.utils.functional import SimpleLazyObject

import six
import logging
from paypalrestsdk import Payment
from paypalrestsdk.exceptions import ResourceNotFound

from danceschool.core.models import TemporaryRegistration, Invoice
from danceschool.core.constants import getConstant

from .models import PaymentRecord

if six.PY3:
    # Ensures that checks for Unicode data types (and unicode type assignments) do not break.
    unicode = str


# Define logger for this file
logger = logging.getLogger(__name__)


def createPaypalPayment(request):
    '''
    This view handles the creation of Paypal Express Checkout Payment objects.

    All Express Checkout payments must either be associated with a pre-existing Invoice
    or a registration, or they must have an amount and type passed in the post data
    (such as gift certificate payment requests).
    '''
    logger.info('Received request for Paypal Express Checkout payment.')

    invoice_id = request.POST.get('invoice_id')
    tr_id = request.POST.get('reg_id')
    amount = request.POST.get('amount')
    submissionUserId = request.POST.get('user_id')
    transactionType = request.POST.get('transaction_type')
    certificateName = request.POST.get('certificate_name')
    taxable = request.POST.get('taxable', False)

    if amount:
        try:
            amount = float(amount)
        except ValueError:
            logger.error('Invalid amount passed.')
            return HttpResponseBadRequest()

    submissionUser = None
    if submissionUserId:
        try:
            submissionUser = User.objects.get(id=int(submissionUserId))
        except (ValueError, ObjectDoesNotExist):
            logger.warning('Invalid user passed, submissionUser will not be recorded.')

    try:
        if invoice_id:
            this_invoice = Invoice.objects.get(id=invoice_id)
            this_description = _('Invoice Payment: %s' % this_invoice.id)
            if not amount:
                amount = this_invoice.outstandingBalance
        elif tr_id:
            tr = TemporaryRegistration.objects.get(id=int(tr_id))
            this_invoice = getattr(tr,'invoice',None)
            if not this_invoice:
                this_invoice = Invoice.create_from_registration(tr, submissionUser=submissionUser)
            this_description = _('Registration Payment: #%s' % tr_id)
            if not amount:
                amount = this_invoice.outstandingBalance
        elif not transactionType or not amount:
            logger.error('Insufficient information passed to createPaypalPayment view.')
            raise ValueError
        else:
            if transactionType == 'Gift Certificate':
                if certificateName:
                    this_description = _('Gift Certificate Purchase for %s' % certificateName)
                else:
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
        logger.error('Invalid registration information passed to createPaypalPayment view: (%s, %s, %s)' % (invoice_id, tr_id, amount))
        logger.error(e)
        return HttpResponseBadRequest()

    this_currency = getConstant('general__currencyCode')

    this_transaction = {
        'amount': {
            'total': min(this_invoice.outstandingBalance, amount),
            'currency': this_currency,
        },
        'description': str(this_description),
        'item_list': {
            'items': []
        }
    }

    for item in this_invoice.invoiceitem_set.all():
        this_transaction['item_list']['items'].append({
            'name': str(item.name),
            'price': item.gross,
            'currency': this_currency,
            'quantity': 1,
        })

    # Paypal requires the Payment request to include redirect URLs.  Since
    # the plugin can handle actual redirects, we just pass the base URL for
    # the current site.
    site = SimpleLazyObject(lambda: get_current_site(request))
    protocol = 'https' if request.is_secure() else 'http'
    base_url = SimpleLazyObject(lambda: "{0}://{1}".format(protocol, site.domain))

    payment = Payment({
        'intent': 'sale',
        'payer': {
            'payment_method': 'paypal'
        },
        'transactions': [this_transaction],
        'redirect_urls': {
            'return_url': str(base_url),
            'cancel_url': str(base_url),
        }
    })

    if payment.create():
        logger.info('Paypal payment object created.')

        if this_invoice:
            this_invoice.status = Invoice.PaymentStatus.authorized
            this_invoice.save()

            # We just keep a record of the ID and the status, because the
            # API can be used to look up everything else.
            PaymentRecord.objects.create(
                paymentId=payment.id,
                invoice=this_invoice,
                status=payment.state,
            )

        return JsonResponse(payment.to_dict())
    else:
        logger.error('Paypal payment object not created.')
        logger.error(payment)
        if this_invoice:
            this_invoice.status = Invoice.PaymentStatus.error
            this_invoice.save()
        return HttpResponseBadRequest()


def executePaypalPayment(request):
    paymentId = request.POST.get('paymentID')
    payerId = request.POST.get('payerID')

    try:
        payment_record = PaymentRecord.objects.get(paymentId=paymentId)
        payment = payment_record.getPayment()
        this_invoice = payment_record.invoice
    except (ResourceNotFound, ObjectDoesNotExist):
        logger.error('Unable to find local record of payment: %s' % paymentId)
        return HttpResponseBadRequest()

    if payment.execute({'payer_id': payerId}):
        payment_record.status = payment.state
        payment_record.payerId = payerId
        payment_record.save()

        this_invoice.processPayment(
            amount=float(payment.transactions[0].amount.total),
            fees=float(payment.transactions[0].related_resources[0].sale.transaction_fee.value),
            paidOnline=True,
            methodName='Paypal Express Checkout',
            methodTxn=paymentId,
        )
        return JsonResponse({'paid': True})
    else:
        this_invoice.status = Invoice.PaymentStatus.error
        this_invoice.save()
        payment_record.status = payment.state
        payment_record.save()
        logger.error()
