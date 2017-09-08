from django.http import HttpResponseRedirect, HttpResponseBadRequest, JsonResponse
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from django.apps import apps

import uuid
from squareconnect.rest import ApiException
from squareconnect.apis.transactions_api import TransactionsApi
import logging
from datetime import timedelta

from danceschool.core.models import TemporaryRegistration, Invoice
from danceschool.core.constants import getConstant, INVOICE_VALIDATION_STR

from .models import SquarePaymentRecord
from .tasks import updateSquareFees


# Define logger for this file
logger = logging.getLogger(__name__)


def processSquarePayment(request):
    '''
    This view handles the charging of approved Square Checkout payments.

    All Checkout payments must either be associated with a pre-existing Invoice
    or a registration, or they must have an amount and type passed in the post data
    (such as gift certificate payment requests).
    '''
    logger.info('Received request for Square Checkout payment.')

    nonce_id = request.POST.get('nonce')
    invoice_id = request.POST.get('invoice_id')
    tr_id = request.POST.get('reg_id')
    amount = request.POST.get('amount')
    submissionUserId = request.POST.get('user_id')
    transactionType = request.POST.get('transaction_type')
    taxable = request.POST.get('taxable', False)
    addSessionInfo = request.POST.get('addSessionInfo',False)
    successUrl = request.POST.get('successUrl')
    customerEmail = request.POST.get('customerEmail')

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
            logger.error('Insufficient information passed to createSquarePayment view.')
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
        logger.error('Invalid registration information passed to createSquarePayment view: (%s, %s, %s)' % (invoice_id, tr_id, amount))
        logger.error(e)
        return HttpResponseBadRequest()

    this_currency = getConstant('general__currencyCode')
    this_total = min(this_invoice.outstandingBalance, amount)

    # TODO: Figure out how to handle taxes
    if not getConstant('registration__buyerPaysSalesTax'):
        pass

    api_instance = TransactionsApi()
    idempotency_key = str(uuid.uuid1())
    location_id = getattr(settings,'SQUARE_LOCATION_ID','')
    amount = {'amount': int(100 * this_total), 'currency': this_currency}
    body = {'idempotency_key': idempotency_key, 'card_nonce': nonce_id, 'amount_money': amount}

    try:
        # Charge
        api_response = api_instance.charge(location_id, body)
        if api_response.errors:
            logger.error('Error in charging Square transaction: %s' % api_response.errors)
            this_invoice.status = Invoice.PaymentStatus.error
            this_invoice.save()
            return HttpResponseBadRequest()
        else:
            logger.info('Square charge successfully created.')
    except ApiException as e:
        logger.error('Exception when calling TransactionApi->charge: %s\n' % e)
        this_invoice.status = Invoice.PaymentStatus.error
        this_invoice.save()
        return HttpResponseBadRequest()

    transaction = api_response.transaction

    paymentRecord = SquarePaymentRecord.objects.create(
        invoice=this_invoice,
        transactionId=transaction.id,
        locationId=transaction.location_id,
    )

    # We process the payment now, and enqueue the job to retrieve the
    # transaction again once fees have been calculated by Square
    this_invoice.processPayment(
        amount=this_total,
        fees=0,
        paidOnline=True,
        methodName='Square Checkout',
        methodTxn=transaction.id,
        notify=customerEmail,
    )
    updateSquareFees.schedule(args=(paymentRecord,), delay=60)

    if addSessionInfo:
        paymentSession = request.session.get(INVOICE_VALIDATION_STR, {})

        paymentSession.update({
            'invoiceID': str(this_invoice.id),
            'amount': this_total,
            'successUrl': successUrl,
        })
        request.session[INVOICE_VALIDATION_STR] = paymentSession

    return HttpResponseRedirect(successUrl)


def processPointOfSalePayment(request):
    '''
    This view handles the callbacks from point-of-sale transactions.
    Please note that this will only work if you have set up your callback
    URL in Square to point to this view.
    '''
    print('Request data is: %s' % request.GET)

    errorCode = request.GET.get('com.squareup.pos.ERROR_CODE')
    errorDescription = request.GET.get('com.squareup.pos.ERROR_DESCRIPTION')
    clientTransId = request.GET.get('com.squareup.pos.CLIENT_TRANSACTION_ID')
    serverTransId = request.GET.get('com.squareup.pos.SERVER_TRANSACTION_ID')
    metadata = request.GET.get('com.squareup.pos.RESULT_REQUEST_METADATA')

    if errorCode:
        logger.warning('Error with square ')
        return JsonResponse({'errorCode': errorCode,'errorDescription': errorDescription})

    if 'registration__' in metadata:
        try:
            tr = TemporaryRegistration.objects.get(id=int(metadata.replace('registration__','')))
        except (ValueError, TypeError, ObjectDoesNotExist):
            pass
    elif 'invoice__' in metadata:
        try:
            inv = Invoice.objects.get(id=int(metadata.replace('invoice__','')))
        except (ValueError, TypeError, ObjectDoesNotExist):
            pass
    elif apps.is_installed('danceschool.financial'):
        RevenueItem = apps.get_model('financial','RevenueItem')
        # The Revenue Item is created using the save() method so that
        # other apps can potentially listen for the RevenueItem pre_save
        # and post_save signals to handle this case.
        ri = RevenueItem(
            category=getConstant(),
            description=metadata,
        )
        ri.save()
    else:
        logger.warning('Unkown Square payment record received; it will be ignored.')

    return HttpResponseRedirect('/')
