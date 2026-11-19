from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpResponseRedirect, HttpResponseBadRequest, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from danceschool.core.constants import getConstant, PAYMENT_VALIDATION_STR
from danceschool.core.models import Invoice
from danceschool.core.views.cart import clear_reg_cart

from .models import StripeCharge, StripeChargeFormModel

import stripe
import logging
from datetime import timedelta


# Define logger for this file
logger = logging.getLogger(__name__)

GIFT_CERTIFICATE = 'Gift Certificate'


def get_success_url(plugin_id):
    '''
    The page to send the payer to after a successful payment: the success
    page of the payment form plugin that they used.  This is looked up on the
    server, rather than accepted from the browser, so that it cannot be used
    to send the payer to another site.
    '''
    try:
        instance = StripeChargeFormModel.objects.get(id=int(plugin_id))
    except (TypeError, ValueError, ObjectDoesNotExist):
        return reverse('registration')
    if instance.successPage:
        return instance.successPage.get_absolute_url()
    return reverse('registration')


def get_local_url(request, url, fallback):
    ''' Return url if it is on this site, otherwise fallback. '''
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return url
    return fallback


@require_POST
def create_checkout_session(request):
    '''
    Create a Stripe Checkout session for a payment, and send the payer to
    Stripe to pay.  A payment is either on an existing invoice (including a
    registration), or a new purchase with an amount and transaction type
    (such as a gift certificate).
    '''
    logger.info('Received request for Stripe Checkout payment.')
    stripe.api_key = settings.STRIPE_PRIVATE_KEY

    amount = request.POST.get('stripeAmount')
    invoice_id = request.POST.get('invoice_id')
    transactionType = request.POST.get('transaction_type')
    taxable = request.POST.get('taxable', False)
    plugin_id = request.POST.get('plugin_id')
    submissionUser = request.user if request.user.is_authenticated else None

    # Payers who leave Stripe without paying go back to the page that they
    # came from.
    if invoice_id:
        sourceFallback = reverse('showRegSummary')
    else:
        sourceFallback = reverse('registration')
    sourceUrl = get_local_url(request, request.POST.get('sourceUrl'), sourceFallback)

    # A specific amount can only be paid for a new purchase (such as a gift
    # certificate); a payment on an invoice pays its balance.
    if amount and not invoice_id:
        try:
            amount = float(amount)
        except ValueError:
            logger.error('Invalid amount passed')
            return HttpResponseBadRequest()

    try:
        # Invoice transactions are usually payment on an existing invoice,
        # including registrations.
        if invoice_id:
            this_invoice = Invoice.objects.get(id=invoice_id)
            if this_invoice.status == Invoice.PaymentStatus.preliminary:
                this_invoice.expirationDate = timezone.now() + timedelta(
                    minutes=getConstant('registration__sessionExpiryMinutes')
                )
            this_invoice.status = Invoice.PaymentStatus.unpaid
            this_description = _('Invoice Payment: %s' % this_invoice.id)
            this_invoice.save()
        # All other transactions require both a transaction type and an amount to be specified
        elif not transactionType or not amount or amount <= 0:
            logger.error('Insufficient information passed to create_checkout_session view.')
            raise ValueError
        else:
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
    except (ValueError, ObjectDoesNotExist) as e:
        logger.error(
            'Invalid invoice/amount information passed to ' +
            'create_checkout_session view: (%s, %s)' % (invoice_id, amount)
        )
        logger.error(e)
        return HttpResponseBadRequest()

    # round() rather than int(), because int() truncates (e.g. int(19.99 * 100) is 1998).
    this_total = round(this_invoice.outstandingBalance * 100)
    if this_total <= 0:
        messages.info(request, _('There is no balance to pay on this invoice.'))
        return HttpResponseRedirect(sourceUrl)

    # Stripe only stores strings in metadata.  Metadata is kept by Stripe
    # and returned with the session, so it is not under the payer's control.
    metadata = {
        'invoice_id': str(this_invoice.id),
        'plugin_id': str(plugin_id or ''),
        'submissionUser': str(submissionUser.id) if submissionUser else '',
        'giftCertificate': 'true' if transactionType == GIFT_CERTIFICATE else '',
    }

    session_kwargs = {
        'mode': 'payment',
        'client_reference_id': str(this_invoice.id),
        'metadata': metadata,
        'line_items': [{
            'quantity': 1,
            'price_data': {
                'currency': getConstant('general__currencyCode').lower(),
                'unit_amount': this_total,
                'product_data': {'name': str(this_description)},
            },
        }],
        # Stripe replaces {CHECKOUT_SESSION_ID} with the session id.
        'success_url': (
            request.build_absolute_uri(reverse('stripeReturn')) +
            '?session_id={CHECKOUT_SESSION_ID}'
        ),
        'cancel_url': request.build_absolute_uri(sourceUrl),
    }
    if this_invoice.email:
        session_kwargs['customer_email'] = this_invoice.email

    try:
        checkout_session = stripe.checkout.Session.create(**session_kwargs)
    except stripe.error.StripeError as e:
        logger.error('Unable to create Stripe Checkout session: %s' % e)
        messages.error(request, _(
            'Unable to start the payment with Stripe. Please try again, or ' +
            'contact us if the problem continues.'
        ))
        return HttpResponseRedirect(sourceUrl)

    return HttpResponseRedirect(checkout_session.url, status=303)


def fulfill_checkout(session_id):
    '''
    Record the payment for a Stripe Checkout session, if it has been paid.
    This is called both when the payer returns to the site and when Stripe
    sends the webhook, whichever comes first, so it records each payment only
    once.  Returns (session, invoice), or (session, None) if the session is
    not for an invoice on this site.
    '''
    session = stripe.checkout.Session.retrieve(
        session_id, expand=['payment_intent.latest_charge.balance_transaction'],
    )
    metadata = session.metadata or {}

    try:
        invoice_id = metadata['invoice_id']
    except KeyError:
        # A session created by something other than this site.
        return session, None

    if session.payment_status != 'paid':
        return session, Invoice.objects.filter(id=invoice_id).first()

    charge = session.payment_intent.latest_charge

    with transaction.atomic():
        # Lock the invoice, so that the return view and the webhook cannot
        # both record the payment at the same time.
        invoice = Invoice.objects.select_for_update().get(id=invoice_id)
        if StripeCharge.objects.filter(chargeId=charge.id).exists():
            return session, invoice

        user = None
        if metadata.get('submissionUser'):
            user = User.objects.filter(id=metadata['submissionUser']).first()

        StripeCharge.objects.create(
            chargeId=charge.id,
            status=charge.status,
            submissionUser=user,
            invoice=invoice,
        )
        invoice.processPayment(
            amount=charge.amount / 100,
            fees=charge.balance_transaction.fee / 100,
            paidOnline=True,
            methodName='Stripe Checkout',
            methodTxn=charge.id,
            submissionUser=user,
            notify=session.customer_details.email if session.customer_details else None,
        )
    return session, invoice


@require_GET
def stripe_return(request):
    '''
    Stripe sends the payer here after they pay.  Record the payment (if the
    webhook has not done so already), clear the registration, and send them
    on to the success page (or to customize their gift certificate).
    '''
    stripe.api_key = settings.STRIPE_PRIVATE_KEY
    session_id = request.GET.get('session_id')
    if not session_id:
        return HttpResponseBadRequest()

    try:
        session, invoice = fulfill_checkout(session_id)
    except stripe.error.StripeError as e:
        logger.error('Unable to retrieve Stripe Checkout session %s: %s' % (session_id, e))
        messages.error(request, _(
            'We were unable to confirm your payment with Stripe. If you were ' +
            'charged, you will receive a confirmation by email.'
        ))
        return HttpResponseRedirect(reverse('registration'))

    if not invoice:
        return HttpResponseBadRequest()

    metadata = session.metadata or {}
    successUrl = get_success_url(metadata.get('plugin_id'))

    if session.payment_status != 'paid':
        # E.g. a bank payment that takes time to complete; the webhook
        # records it when it does.
        messages.info(request, _(
            'Your payment is being processed. You will receive a confirmation ' +
            'by email when it is complete.'
        ))
        return HttpResponseRedirect(successUrl)

    clear_reg_cart(request)

    if metadata.get('giftCertificate'):
        paymentSession = request.session.get(PAYMENT_VALIDATION_STR, {})
        paymentSession.update({
            'invoiceID': str(invoice.id),
            'amount': session.amount_total / 100,
            'successUrl': successUrl,
        })
        request.session[PAYMENT_VALIDATION_STR] = paymentSession
        return HttpResponseRedirect(reverse('customizeGiftCertificate'))

    return HttpResponseRedirect(successUrl)


# Stripe calls this, so it cannot send a CSRF token; the request is verified
# by its signature instead.
@csrf_exempt
@require_POST
def webhook(request):
    stripe.api_key = settings.STRIPE_PRIVATE_KEY
    payload = request.body
    endpoint_secret = settings.STRIPE_WEBHOOK_KEY
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    if not sig_header:
        return HttpResponse(status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError:
        # Invalid payload
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        return HttpResponse(status=400)

    session = event['data']['object']

    if event['type'] in [
        'checkout.session.completed', 'checkout.session.async_payment_succeeded'
    ]:
        fulfill_checkout(session['id'])

    elif event['type'] in [
        'checkout.session.async_payment_failed', 'checkout.session.expired'
    ]:
        # Only an invoice that is still waiting for this payment is marked as
        # an error; it may since have been paid in some other way.
        invoice_id = (session.get('metadata') or {}).get('invoice_id')
        invoice = Invoice.objects.filter(id=invoice_id).first() if invoice_id else None
        if (
            invoice and invoice.status == Invoice.PaymentStatus.unpaid and
            not invoice.amountPaid
        ):
            invoice.status = Invoice.PaymentStatus.error
            invoice.save()

    # Passed signature verification
    return HttpResponse(status=200)


class SuccessView(TemplateView):
    template_name = 'stripe/success.html'


class CancelledView(TemplateView):
    template_name = 'stripe/cancelled.html'
