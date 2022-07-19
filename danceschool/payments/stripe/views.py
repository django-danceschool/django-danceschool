from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect, HttpResponseBadRequest, HttpResponse
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from danceschool.core.constants import getConstant, PAYMENT_VALIDATION_STR
from danceschool.core.models import Invoice

from .models import StripeCharge

import stripe
import logging
from datetime import timedelta


# Define logger for this file
logger = logging.getLogger(__name__)


def handle_stripe_checkout(request):

    logger.info('Received request for Stripe Checkout payment.')

    stripeToken = request.POST.get('stripeToken')
    stripeEmail = request.POST.get('stripeEmail')
    submissionUserId = request.POST.get('submissionUser')
    amount = request.POST.get('stripeAmount')
    invoice_id = request.POST.get('invoice_id')
    transactionType = request.POST.get('transaction_type')
    taxable = request.POST.get('taxable', False)
    addSessionInfo = request.POST.get('addSessionInfo', False)
    customizeUrl = request.POST.get('customizeUrl')
    successUrl = request.POST.get('successUrl', reverse('registration'))

    # Parse if a specific submission user is indicated
    submissionUser = None
    if submissionUserId:
        try:
            submissionUser = User.objects.get(id=int(submissionUserId))
        except (ValueError, ObjectDoesNotExist):
            logger.warning('Invalid user passed, submissionUser will not be recorded.')

    # If a specific amount to pay has been passed, then allow payment
    # of that amount.
    if amount:
        try:
            if isinstance(amount, list):
                amount = float(amount[0])
            else:
                amount = float(amount)
        except ValueError:
            logger.error('Invalid amount passed')
            return HttpResponseBadRequest()

    # If the details of this transaction are to be entered into session info, then
    # the view must redirect to an interim URL (e.g. for gift certificates) that
    # handles that data
    if addSessionInfo and not customizeUrl:
        logger.error('Request to pass session info without specifying interim URL.')
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
            if not amount:
                amount = this_invoice.outstandingBalance
            this_invoice.save()
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
                status=Invoice.PaymentStatus.unpaid,
            )
    except (ValueError, ObjectDoesNotExist) as e:
        logger.error(
            'Invalid invoice/amount information passed to ' +
            'handle_stripe_checkout view: (%s, %s)' % (
                invoice_id, amount
            )
        )
        logger.error(e)
        return HttpResponseBadRequest()

    this_invoice.status = Invoice.PaymentStatus.unpaid

    this_total = int(min(this_invoice.outstandingBalance, amount) * 100)
    charge = None

    try:
        # Use Stripe's library to make requests...
        charge = stripe.Charge.create(
            amount=this_total,
            currency=getConstant('general__currencyCode'),
            description=this_description,
            source=stripeToken,
        )

    except stripe.error.CardError as e:
        # Since it's a decline, stripe.error.CardError will be caught
        body = e.json_body
        err = body['error']
        logger.error('Stripe CardError %s: %s' % (e.http_status, err))
    except stripe.error.RateLimitError as e:
        # Too many requests made to the API too quickly
        body = e.json_body
        err = body['error']
        logger.error('Stripe RateLimitError %s: %s' % (e.http_status, err))
    except stripe.error.InvalidRequestError as e:
        # Invalid parameters were supplied to Stripe's API
        body = e.json_body
        err = body['error']
        logger.error('Stripe InvalidRequestError %s: %s' % (e.http_status, err))
    except stripe.error.AuthenticationError as e:
        # Authentication with Stripe's API failed
        # (maybe you changed API keys recently)
        body = e.json_body
        err = body['error']
        logger.error('Stripe AuthenticationError %s: %s' % (e.http_status, err))
    except stripe.error.APIConnectionError as e:
        # Network communication with Stripe failed
        body = e.json_body
        err = body['error']
        logger.error('Stripe APIConnectionError %s: %s' % (e.http_status, err))
    except stripe.error.StripeError as e:
        # Display a very generic error to the user, and maybe send
        # yourself an email
        body = e.json_body
        err = body['error']
        logger.error('Stripe StripeError %s: %s' % (e.http_status, err))

    if charge:
        StripeCharge.objects.create(
            chargeId=charge.id,
            status=charge.status,
            submissionUser=submissionUser,
            invoice=this_invoice,
        )

        # To determine the fees applied, we also need to get the balanceTransaction
        # that reports them.
        balanceTransaction = stripe.BalanceTransaction.retrieve(charge.balance_transaction)

        this_invoice.processPayment(
            amount=charge.amount / 100,
            fees=balanceTransaction.fee / 100,
            paidOnline=True,
            methodName='Stripe Checkout',
            methodTxn=charge.id,
            submissionUser=submissionUser,
            notify=stripeEmail,
        )

        if addSessionInfo:
            paymentSession = request.session.get(PAYMENT_VALIDATION_STR, {})

            paymentSession.update({
                'invoiceID': str(this_invoice.id),
                'amount': charge.amount / 100,
                'successUrl': successUrl,
            })
            request.session[PAYMENT_VALIDATION_STR] = paymentSession
            return HttpResponseRedirect(customizeUrl)

        return HttpResponseRedirect(successUrl)

    else:
        this_invoice.status = Invoice.PaymentStatus.error
        this_invoice.save()
        return JsonResponse(err)


@csrf_exempt
def create_checkout_session(request):
    if request.method == 'POST':
        domain_url = settings.DOMAIN_URL
        stripe.api_key = settings.STRIPE_PRIVATE_KEY

        logger.info('Received request for Stripe Checkout payment.')
        submissionUserId = request.POST.get('submissionUser')
        amount = request.POST.get('stripeAmount')
        invoice_id = request.POST.get('invoice_id')
        transactionType = request.POST.get('transaction_type')
        taxable = request.POST.get('taxable', False)
        addSessionInfo = request.POST.get('addSessionInfo', False)
        customizeUrl = request.POST.get('customizeUrl')
        successUrl = request.POST.get('successUrl', reverse('registration'))

        # Parse if a specific submission user is indicated
        submissionUser = None
        if submissionUserId:
            try:
                submissionUser = User.objects.get(id=int(submissionUserId))
            except (ValueError, ObjectDoesNotExist):
                logger.warning('Invalid user passed, submissionUser will not be recorded.')

        # If a specific amount to pay has been passed, then allow payment
        # of that amount.
        if amount:
            try:
                if isinstance(amount, list):
                    amount = float(amount[0])
                else:
                    amount = float(amount)
            except ValueError:
                logger.error('Invalid amount passed')
                return HttpResponseBadRequest()

        # If the details of this transaction are to be entered into session info, then
        # the view must redirect to an interim URL (e.g. for gift certificates) that
        # handles that data
        if addSessionInfo and not customizeUrl:
            logger.error('Request to pass session info without specifying interim URL.')
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
                if not amount:
                    amount = this_invoice.outstandingBalance
                this_invoice.save()
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
                    status=Invoice.PaymentStatus.unpaid,
                )
        except (ValueError, ObjectDoesNotExist) as e:
            logger.error(
                'Invalid invoice/amount information passed to ' +
                'handle_stripe_checkout view: (%s, %s)' % (
                    invoice_id, amount
                )
            )
            logger.error(e)
            return HttpResponseBadRequest()

        this_invoice.status = Invoice.PaymentStatus.unpaid
        stripeEmail = this_invoice.email
        this_total = int(min(this_invoice.outstandingBalance, amount) * 100)
        try:
            # Create new Checkout Session for the order
            # Other optional params include:
            # [billing_address_collection] - to display billing address details on the page
            # [customer] - if you have an existing Stripe Customer ID
            # [payment_intent_data] - capture the payment later
            # [customer_email] - prefill the email input in the form
            # For full details see https://stripe.com/docs/api/checkout/sessions/create

            metadata = {
                'invoice_id': this_invoice.id,
                'submissionUser': submissionUser.id if submissionUser else None,
                'stripeEmail': stripeEmail,
                'addSessionInfo': addSessionInfo if addSessionInfo else None,
                'successUrl': domain_url + successUrl,
                'customizeUrl': customizeUrl if customizeUrl else None,
            }
            # ?session_id={CHECKOUT_SESSION_ID} means the redirect will have the session ID set as a query param
            checkout_session = stripe.checkout.Session.create(
                client_reference_id=request.user.id if request.user.is_authenticated else None,
                success_url=domain_url + successUrl,
                cancel_url=domain_url + '/registration/summary/',
                payment_method_types=['card', 'p24'],
                mode='payment',
                customer_email=stripeEmail,
                metadata=metadata,
                line_items=[
                    {
                        'name': this_description,
                        'quantity': 1,
                        'currency': getConstant('general__currencyCode'),
                        'amount': this_total,
                    }
                ]
            )
        except Exception as e:
            return str(e)

        return redirect(checkout_session.url, code=303)


# You can find your endpoint's secret in your webhook settings
@csrf_exempt
def webhook(request):
    payload = request.body
    endpoint_secret = settings.STRIPE_WEBHOOK_KEY
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )

    except ValueError as e:
        # Invalid payload
        return HttpResponse(status=400)

    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return HttpResponse(status=400)

    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        if session.payment_status == "paid":
            payment_intent = stripe.PaymentIntent.retrieve(session['payment_intent'])
            charges = payment_intent['charges']
            metadata = session['metadata']
            for charge in charges:
                finish_order(charge, metadata, request)

    elif event['type'] == 'checkout.session.async_payment_succeeded':
        session = event['data']['object']
        if session.payment_status == "paid":
            payment_intent = stripe.PaymentIntent.retrieve(session['payment_intent'])
            charges = payment_intent['charges']
            metadata = session['metadata']
            for charge in charges:
                finish_order(charge, metadata, request)

    elif event['type'] == 'checkout.session.async_payment_failed':
        session = event['data']['object']
        metadata = session['metadata']
        invoice = Invoice.objects.get(id=metadata['invoice_id'])
        invoice.status = Invoice.PaymentStatus.error
        invoice.save()

    elif event['type'] == 'checkout.session.expired':
        session = event['data']['object']
        metadata = session['metadata']
        invoice = Invoice.objects.get(id=metadata['invoice_id'])
        invoice.status = Invoice.PaymentStatus.error
        invoice.save()

    # Passed signature verification
    return HttpResponse(status=200)


def finish_order(charge, metadata, request):
    invoice = Invoice.objects.get(id=metadata['invoice_id'])
    if 'submissionUser' in metadata:
        user = User.objects.get(id=metadata['submissionUser'])
    else:
        user = None

    StripeCharge.objects.create(
        chargeId=charge.id,
        status=charge.status,
        submissionUser=user,
        invoice=invoice,
    )

    # To determine the fees applied, we also need to get the balanceTransaction
    # that reports them.
    balanceTransaction = stripe.BalanceTransaction.retrieve(charge.balance_transaction)

    invoice.processPayment(
        amount=charge.amount / 100,
        fees=balanceTransaction.fee / 100,
        paidOnline=True,
        methodName='Stripe Checkout',
        methodTxn=charge.id,
        submissionUser=user,
        notify=metadata['stripeEmail'],
    )

    if 'addSessionInfo' in metadata:
        paymentSession = request.session.get(PAYMENT_VALIDATION_STR, {})

        paymentSession.update({
            'invoiceID': str(invoice.id),
            'amount': charge.amount / 100,
            'successUrl': metadata['successUrl'],
        })
        request.session[PAYMENT_VALIDATION_STR] = paymentSession
        if 'customizeUrl' in metadata:
            return HttpResponseRedirect(metadata['customizeUrl'])

    if 'successUrl' in metadata:
        return HttpResponseRedirect(metadata['successUrl'])


class SuccessView(TemplateView):
    template_name = 'stripe/success.html'


class CancelledView(TemplateView):
    template_name = 'stripe/cancelled.html'
