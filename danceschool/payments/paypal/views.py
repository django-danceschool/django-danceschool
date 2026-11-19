from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

import logging
from datetime import timedelta

from paypalserversdk.exceptions.api_exception import ApiException
from paypalserversdk.models.amount_with_breakdown import AmountWithBreakdown
from paypalserversdk.models.checkout_payment_intent import CheckoutPaymentIntent
from paypalserversdk.models.order_request import OrderRequest
from paypalserversdk.models.purchase_unit_request import PurchaseUnitRequest

from danceschool.core.models import Invoice
from danceschool.core.constants import getConstant, PAYMENT_VALIDATION_STR
from danceschool.core.helpers import (
    getBalanceChangedMessage, getLocalUrl, getPluginSuccessUrl
)
from danceschool.core.views.cart import clear_reg_cart

from . import api_client
from .models import PaypalPaymentRecord, PayNowFormModel


# Define logger for this file
logger = logging.getLogger(__name__)

GIFT_CERTIFICATE = 'Gift Certificate'

# The details of each order that this payer has started, kept in their
# session so that they are not taken from the browser when the order is
# captured.
ORDERS_SESSION_KEY = 'paypal_orders'

UNKNOWN_ERROR = _(
    'An unknown error has occurred. Please try again, or notify us if you ' +
    'continue to have an issue.'
)


def error_response(message, redirect_url=None, status=400):
    data = {'status': 'error', 'message': str(message)}
    if redirect_url:
        data['redirect_url'] = redirect_url
    return JsonResponse(data, status=status)


def order_amount(order):
    ''' The amount of a PayPal order, as a float. '''
    return float(order.purchase_units[0].amount.value)


@require_POST
def createPaypalOrder(request):
    '''
    Create a PayPal order for the PayPal button.  A payment is either on an
    existing invoice (including a registration), or a new purchase with an
    amount and transaction type (such as a gift certificate).  Nothing is
    charged until the payer approves the order and it is captured.
    '''
    logger.info('Received request for PayPal order.')

    invoice_id = request.POST.get('invoice_id')
    amount = request.POST.get('amount')
    transactionType = request.POST.get('transaction_type')
    taxable = request.POST.get('taxable', False)
    plugin_id = request.POST.get('plugin_id')
    expectedBalance = request.POST.get('expected_balance') if invoice_id else None
    submissionUser = request.user if request.user.is_authenticated else None

    # Payers whose payment cannot be made go back to the page that they came
    # from.
    sourceUrl = getLocalUrl(
        request, request.POST.get('sourceUrl'),
        reverse('showRegSummary') if invoice_id else reverse('registration')
    )

    try:
        # A specific amount can only be paid for a new purchase (such as a
        # gift certificate); a payment on an invoice pays its balance.
        if invoice_id:
            this_invoice = Invoice.objects.get(id=invoice_id)

            # Do not start a payment of a balance other than the one that the
            # payer was shown (e.g. if staff changed the invoice while they
            # were paying, or if it has already been paid).
            if expectedBalance is not None:
                expectedBalance = float(expectedBalance)
                balance = this_invoice.outstandingBalance
                if abs(balance - expectedBalance) >= 0.01:
                    logger.warning(
                        'Refused PayPal payment on invoice %s: the payer was '
                        'shown a balance of %.2f, but the balance is now %.2f.' % (
                            this_invoice.id, expectedBalance, balance
                        )
                    )
                    return error_response(getBalanceChangedMessage(balance), sourceUrl)

            if this_invoice.status == Invoice.PaymentStatus.preliminary:
                this_invoice.expirationDate = timezone.now() + timedelta(
                    minutes=getConstant('registration__sessionExpiryMinutes')
                )
                this_invoice.status = Invoice.PaymentStatus.unpaid
                this_invoice.save()
            this_description = _('Invoice Payment: %s' % this_invoice.id)
        else:
            amount = float(amount or 0)
            if not transactionType or amount <= 0:
                logger.error('Insufficient information passed to createPaypalOrder view.')
                raise ValueError
            # Gift certificates automatically get a nicer invoice description
            if transactionType == GIFT_CERTIFICATE:
                this_description = _('Gift Certificate Purchase')
            else:
                this_description = transactionType
            this_invoice = Invoice.create_from_item(
                amount,
                this_description,
                submissionUser=submissionUser,
                calculate_taxes=(taxable is not False),
                transactionType=transactionType,
                status=Invoice.PaymentStatus.unpaid,
            )
    except (ValueError, TypeError, ObjectDoesNotExist) as e:
        logger.error(
            'Invalid invoice/amount information passed to createPaypalOrder ' +
            'view: (%s, %s): %s' % (invoice_id, amount, e)
        )
        return error_response(UNKNOWN_ERROR)

    this_total = this_invoice.outstandingBalance
    if this_total <= 0:
        return error_response(_('There is no balance to pay on this invoice.'), sourceUrl)

    # The order is for the balance as a whole.  PayPal requires an itemized
    # order to add up exactly, including discounts, taxes and adjustments,
    # and the payer gains little from seeing the items again.
    body = OrderRequest(
        intent=CheckoutPaymentIntent.CAPTURE,
        purchase_units=[PurchaseUnitRequest(
            amount=AmountWithBreakdown(
                currency_code=getConstant('general__currencyCode'),
                value='%.2f' % this_total,
            ),
            custom_id=str(this_invoice.id),
            description=str(this_description)[:127],
        )],
    )

    try:
        order = api_client.get_client().orders.create_order({
            'body': body, 'prefer': 'return=minimal',
        }).body
    except ApiException as e:
        logger.error('Unable to create PayPal order: %s' % api_client.error_message(e))
        return error_response(_(
            'Unable to start the payment with PayPal. Please try again, or ' +
            'contact us if the problem continues.'
        ), sourceUrl)

    PaypalPaymentRecord.objects.create(
        paymentId=order.id,
        invoice=this_invoice,
        status=order.status,
        submissionUser=submissionUser,
    )

    orders = request.session.get(ORDERS_SESSION_KEY, {})
    orders[order.id] = {
        'plugin_id': str(plugin_id or ''),
        'giftCertificate': transactionType == GIFT_CERTIFICATE and not invoice_id,
        'sourceUrl': sourceUrl,
    }
    request.session[ORDERS_SESSION_KEY] = orders

    return JsonResponse({'id': order.id})


def notify_pending(invoice, record, capture):
    ''' Email staff about a PayPal payment that PayPal is holding as pending. '''
    reason = getattr(getattr(capture, 'status_details', None), 'reason', None)
    invoice.emailStaff(
        _('PayPal payment pending on invoice %s') % invoice.id,
        str(_(
            'This is an automated notice that PayPal is holding a payment as ' +
            'pending (for example, an eCheck that has not cleared), so it has ' +
            'not been recorded on the invoice. Once PayPal completes the ' +
            'payment, record it on the invoice.'
        )),
        [
            str(_('Amount: %s%s') % (
                getConstant('general__currencySymbol'), capture.amount.value
            )),
            str(_('PayPal order: %s') % record.paymentId),
            str(_('PayPal capture: %s') % capture.id),
            str(_('Reason: %s') % (reason or _('not given'))),
        ],
    )


@require_POST
def capturePaypalOrder(request):
    '''
    Capture a PayPal order that the payer has approved, and record the
    payment.  The order is only captured if the balance of the invoice is
    still the amount of the order; otherwise, nothing is charged.
    '''
    order_id = request.POST.get('orderID')
    details = request.session.get(ORDERS_SESSION_KEY, {}).get(order_id, {})
    sourceUrl = details.get('sourceUrl') or reverse('registration')

    try:
        record = PaypalPaymentRecord.objects.get(paymentId=order_id)
    except ObjectDoesNotExist:
        logger.error('Unable to find local record of PayPal order: %s' % order_id)
        return HttpResponseBadRequest()

    client = api_client.get_client()

    with transaction.atomic():
        # Lock the record, so that a second request (e.g. a double click)
        # waits for this one, and then finds the order already captured.
        record = PaypalPaymentRecord.objects.select_for_update().get(id=record.id)
        invoice = Invoice.objects.select_for_update().get(id=record.invoice_id)

        if not record.captureId:
            try:
                order = client.orders.get_order({'id': order_id}).body
            except ApiException as e:
                logger.error(
                    'Unable to retrieve PayPal order %s: %s' %
                    (order_id, api_client.error_message(e))
                )
                return error_response(UNKNOWN_ERROR)

            expectedBalance = order_amount(order)
            balance = invoice.outstandingBalance
            if abs(balance - expectedBalance) >= 0.01:
                logger.warning(
                    'Did not capture PayPal order %s on invoice %s: the order is '
                    'for %.2f, but the balance is now %.2f.' % (
                        order_id, invoice.id, expectedBalance, balance
                    )
                )
                record.status = 'NOT_CAPTURED'
                record.save()
                return error_response(getBalanceChangedMessage(balance), sourceUrl)

            try:
                result = client.orders.capture_order({
                    'id': order_id,
                    'prefer': 'return=representation',
                    # Ensures that the order is not captured twice if the
                    # request is retried.
                    'paypal_request_id': 'capture-%s' % order_id,
                }).body
            except ApiException as e:
                # E.g. the payer's funding source was declined.
                logger.error(
                    'Unable to capture PayPal order %s: %s' %
                    (order_id, api_client.error_message(e))
                )
                record.status = 'CAPTURE_FAILED'
                record.save()
                return error_response(_(
                    'PayPal was unable to complete your payment, and you have ' +
                    'not been charged. Please try again, or use another ' +
                    'payment method.'
                ))

            capture = result.purchase_units[0].payments.captures[0]
            record.status = capture.status
            record.captureId = capture.id
            record.payerId = getattr(getattr(result, 'payer', None), 'payer_id', None)
            record.save()

            if capture.status == 'COMPLETED':
                breakdown = getattr(capture, 'seller_receivable_breakdown', None)
                fee = getattr(breakdown, 'paypal_fee', None)
                invoice.processPayment(
                    amount=float(capture.amount.value),
                    fees=float(fee.value) if fee else 0,
                    paidOnline=True,
                    methodName='Paypal Express Checkout',
                    methodTxn=capture.id,
                    submissionUser=record.submissionUser,
                    notify=getattr(getattr(result, 'payer', None), 'email_address', None),
                    expectedBalance=expectedBalance,
                )
            elif capture.status == 'PENDING':
                logger.warning('PayPal capture %s is pending.' % capture.id)
                notify_pending(invoice, record, capture)
            else:
                logger.error('PayPal capture %s has status %s.' % (capture.id, capture.status))
                return error_response(_(
                    'PayPal was unable to complete your payment. Please try ' +
                    'again, or use another payment method.'
                ))

    successUrl = (
        getPluginSuccessUrl(PayNowFormModel, details.get('plugin_id')) or
        reverse('registration')
    )

    if record.status == 'PENDING':
        clear_reg_cart(request)
        return JsonResponse({
            'status': 'pending',
            'message': str(_(
                'PayPal is still processing your payment. We will confirm ' +
                'your registration once the payment is complete.'
            )),
            'redirect_url': successUrl,
        })

    clear_reg_cart(request)

    if details.get('giftCertificate'):
        paymentSession = request.session.get(PAYMENT_VALIDATION_STR, {})
        paymentSession.update({
            'invoiceID': str(invoice.id),
            'amount': invoice.amountPaid,
            'successUrl': successUrl,
        })
        request.session[PAYMENT_VALIDATION_STR] = paymentSession
        return JsonResponse({
            'status': 'success', 'redirect_url': reverse('customizeGiftCertificate'),
        })

    return JsonResponse({'status': 'success', 'redirect_url': successUrl})
