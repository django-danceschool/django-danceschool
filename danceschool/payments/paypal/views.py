from django.http import JsonResponse, HttpResponseBadRequest
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.utils.functional import SimpleLazyObject
from django.utils import timezone

import logging
from paypalrestsdk import Payment
from paypalrestsdk.exceptions import ResourceNotFound
from datetime import timedelta

from danceschool.core.models import TemporaryRegistration, Invoice
from danceschool.core.constants import getConstant, INVOICE_VALIDATION_STR

from .models import PaypalPaymentRecord


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
            tr.expirationDate = timezone.now() + timedelta(minutes=getConstant('registration__sessionExpiryMinutes'))
            tr.save()
            this_invoice = Invoice.get_or_create_from_registration(tr, submissionUser=submissionUser)
            this_description = _('Registration Payment: #%s' % tr_id)
            if not amount:
                amount = this_invoice.outstandingBalance
        # All other transactions require both a transaction type and an amount to be specified
        elif not transactionType or not amount:
            logger.error('Insufficient information passed to createPaypalPayment view.')
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
        logger.error('Invalid registration information passed to createPaypalPayment view: (%s, %s, %s)' % (invoice_id, tr_id, amount))
        logger.error(e)
        return HttpResponseBadRequest()

    this_currency = getConstant('general__currencyCode')

    this_total = min(this_invoice.outstandingBalance, amount)
    this_subtotal = this_total - this_invoice.taxes

    this_transaction = {
        'amount': {
            'total': round(this_total,2),
            'currency': this_currency,
            'details': {
                'subtotal': round(this_subtotal,2),
                'tax': round(this_invoice.taxes,2),
            },
        },
        'description': str(this_description),
        'item_list': {
            'items': []
        }
    }

    for item in this_invoice.invoiceitem_set.all():

        if not getConstant('registration__buyerPaysSalesTax'):
            this_item_price = item.grossTotal - item.taxes
        else:
            this_item_price = item.grossTotal

        this_transaction['item_list']['items'].append({
            'name': str(item.name),
            'price': round(this_item_price,2),
            'tax': round(item.taxes,2),
            'currency': this_currency,
            'quantity': 1,
        })

    # Because the Paypal API requires that the subtotal add up to the sum of the item
    # totals, we must add a negative line item for discounts applied, and a line item
    # for the remaining balance if there is to be one.
    if this_invoice.grossTotal != this_invoice.total:
        this_transaction['item_list']['items'].append({
            'name': str(_('Total Discounts')),
            'price': round(this_invoice.total,2) - round(this_invoice.grossTotal,2),
            'currency': this_currency,
            'quantity': 1,
        })
    if this_invoice.amountPaid > 0:
        this_transaction['item_list']['items'].append({
            'name': str(_('Previously Paid')),
            'price': -1 * round(this_invoice.amountPaid,2),
            'currency': this_currency,
            'quantity': 1,
        })
    if amount != this_invoice.outstandingBalance:
        this_transaction['item_list']['items'].append({
            'name': str(_('Remaining Balance After Payment')),
            'price': round(amount,2) - round(this_invoice.outstandingBalance,2),
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
            PaypalPaymentRecord.objects.create(
                paymentId=payment.id,
                invoice=this_invoice,
                status=payment.state,
            )

        return JsonResponse(payment.to_dict())
    else:
        logger.error('Paypal payment object not created.')
        logger.error(payment)
        logger.error(payment.error)
        if this_invoice:
            this_invoice.status = Invoice.PaymentStatus.error
            this_invoice.save()
        return HttpResponseBadRequest()


def executePaypalPayment(request):
    paymentId = request.POST.get('paymentID')
    payerId = request.POST.get('payerID')
    addSessionInfo = request.POST.get('addSessionInfo',False)
    successUrl = request.POST.get('successUrl')

    try:
        payment_record = PaypalPaymentRecord.objects.get(paymentId=paymentId)
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
            notify=payment.payer.payer_info.email,
        )

        if addSessionInfo:
            paymentSession = request.session.get(INVOICE_VALIDATION_STR, {})

            paymentSession.update({
                'invoiceID': str(this_invoice.id),
                'amount': float(payment.transactions[0].amount.total),
                'successUrl': successUrl,
            })
            request.session[INVOICE_VALIDATION_STR] = paymentSession

        return JsonResponse({'paid': True})
    else:
        this_invoice.status = Invoice.PaymentStatus.error
        this_invoice.save()
        payment_record.status = payment.state
        payment_record.save()
        logger.error()
