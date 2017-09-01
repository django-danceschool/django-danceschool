from django.http import JsonResponse, HttpResponseRedirect, HttpResponseBadRequest
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from danceschool.core.constants import getConstant, INVOICE_VALIDATION_STR
from danceschool.core.models import Invoice, TemporaryRegistration

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
    tr_id = request.POST.get('reg_id')
    transactionType = request.POST.get('transaction_type')
    taxable = request.POST.get('taxable', False)
    addSessionInfo = request.POST.get('addSessionInfo',False)
    customizeUrl = request.POST.get('customizeUrl')
    successUrl = request.POST.get('successUrl',reverse('registration'))

    # Parse if a specific submission user is indicated
    submissionUser = None
    if submissionUserId:
        try:
            submissionUser = User.objects.get(id=int(submissionUserId))
        except (ValueError,ObjectDoesNotExist):
            logger.warning('Invalid user passed, submissionUser will not be recorded.')

    # If a specific amount to pay has been passed, then allow payment
    # of that amount.
    if amount:
        try:
            if isinstance(amount,list):
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
        logger.error('Invalid registration information passed to handle_stripe_checkout view: (%s, %s, %s)' % (invoice_id, tr_id, amount))
        logger.error(e)
        return HttpResponseBadRequest()

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
        logger.error('Stripe CardError %s: %s' % (e.http_status,err))
    except stripe.error.RateLimitError as e:
        # Too many requests made to the API too quickly
        body = e.json_body
        err = body['error']
        logger.error('Stripe RateLimitError %s: %s' % (e.http_status,err))
    except stripe.error.InvalidRequestError as e:
        # Invalid parameters were supplied to Stripe's API
        body = e.json_body
        err = body['error']
        logger.error('Stripe InvalidRequestError %s: %s' % (e.http_status,err))
    except stripe.error.AuthenticationError as e:
        # Authentication with Stripe's API failed
        # (maybe you changed API keys recently)
        body = e.json_body
        err = body['error']
        logger.error('Stripe AuthenticationError %s: %s' % (e.http_status,err))
    except stripe.error.APIConnectionError as e:
        # Network communication with Stripe failed
        body = e.json_body
        err = body['error']
        logger.error('Stripe APIConnectionError %s: %s' % (e.http_status,err))
    except stripe.error.StripeError as e:
        # Display a very generic error to the user, and maybe send
        # yourself an email
        body = e.json_body
        err = body['error']
        logger.error('Stripe StripeError %s: %s' % (e.http_status,err))

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
            paymentSession = request.session.get(INVOICE_VALIDATION_STR, {})

            paymentSession.update({
                'invoiceID': str(this_invoice.id),
                'amount': charge.amount / 100,
                'successUrl': successUrl,
            })
            request.session[INVOICE_VALIDATION_STR] = paymentSession
            return HttpResponseRedirect(customizeUrl)

        return HttpResponseRedirect(successUrl)

    else:
        # TODO: Improve error handling.
        return JsonResponse(err)
