from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from django.contrib import messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe

import uuid
from squareconnect.rest import ApiException
from squareconnect.apis.transactions_api import TransactionsApi
import logging
from datetime import timedelta
import json
from base64 import b64decode
import binascii
from urllib.parse import unquote

from danceschool.core.models import Invoice
from danceschool.core.constants import getConstant, PAYMENT_VALIDATION_STR

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
    idempotency_key = request.POST.get('idempotency_key', str(uuid.uuid1()))
    invoice_id = request.POST.get('invoice_id')
    amount = request.POST.get('amount')
    submissionUserId = request.POST.get('user_id')
    transactionType = request.POST.get('transaction_type')
    taxable = request.POST.get('taxable', False)
    sourceUrl = request.POST.get('sourceUrl', reverse('showRegSummary'))
    addSessionInfo = request.POST.get('addSessionInfo', False)
    successUrl = request.POST.get('successUrl', reverse('registration'))
    customerEmail = request.POST.get('customerEmail')

    # If a specific amount to pay has been passed, then allow payment
    # of that amount.
    if amount:
        try:
            amount = float(amount)
        except ValueError:
            logger.error('Invalid amount passed')
            messages.error(
                request,
                format_html(
                    '<p>{}</p><ul><li>{}</li></ul>',
                    str(_('ERROR: Error with Square checkout transaction attempt.')),
                    str(_('Invalid amount passed.'))
                )
            )
            return HttpResponseRedirect(sourceUrl)

    # Parse if a specific submission user is indicated
    submissionUser = None
    if submissionUserId:
        try:
            submissionUser = User.objects.get(id=int(submissionUserId))
        except (ValueError, ObjectDoesNotExist):
            logger.warning('Invalid user passed, submissionUser will not be recorded.')

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
            logger.error('Insufficient information passed to createSquarePayment view.')
            messages.error(
                request,
                format_html(
                    '<p>{}</p><ul><li>{}</li></ul>',
                    str(_('ERROR: Error with Square checkout transaction attempt.')),
                    str(_('Insufficient information passed to createSquarePayment view.'))
                )
            )
            return HttpResponseRedirect(sourceUrl)
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
            'Invalid invoice/amount information passed to createSquarePayment ' +
            'view: (%s, %s)' % (invoice_id, amount)
        )
        messages.error(
            request,
            format_html(
                '<p>{}</p><ul><li>{}</li></ul>',
                str(_('ERROR: Error with Square checkout transaction attempt.')),
                str(_(
                    'Invalid invoice/amount information passed to ' +
                    'createSquarePayment view: (%s, %s)' % (
                        invoice_id, amount
                    )
                ))
            )
        )
        return HttpResponseRedirect(sourceUrl)

    if this_invoice.status == Invoice.PaymentStatus.preliminary:
        this_invoice.status = Invoice.PaymentStatus.unpaid

    this_currency = getConstant('general__currencyCode')
    this_total = min(this_invoice.outstandingBalance, amount)

    api_instance = TransactionsApi()
    api_instance.api_client.configuration.access_token = getattr(settings, 'SQUARE_ACCESS_TOKEN', '')
    location_id = getattr(settings, 'SQUARE_LOCATION_ID', '')
    amount = {'amount': int(100 * this_total), 'currency': this_currency}
    body = {'idempotency_key': idempotency_key, 'card_nonce': nonce_id, 'amount_money': amount}

    errors_list = []

    try:
        # Charge
        api_response = api_instance.charge(location_id, body)
        if api_response.errors:
            logger.error('Error in charging Square transaction: %s' % api_response.errors)
            errors_list = api_response.errors
    except ApiException as e:
        logger.error('Exception when calling TransactionApi->charge: %s\n' % e)
        errors_list = json.loads(e.body).get('errors', [])

    if errors_list:
        this_invoice.status = Invoice.PaymentStatus.error
        this_invoice.save()
        errors_string = ''
        for err in errors_list:
            errors_string += '<li><strong>CODE:</strong> %s, %s</li>' % (
                err.get('code', str(_('Unknown'))), err.get('detail', str(_('Unknown')))
            )
        messages.error(
            request,
            format_html(
                '<p>{}</p><ul>{}</ul>',
                str(_('ERROR: Error with Square checkout transaction attempt.')),
                mark_safe(errors_list),
            )
        )
        return HttpResponseRedirect(sourceUrl)
    else:
        logger.info('Square charge successfully created.')

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
    updateSquareFees.schedule(args=(paymentRecord, ), delay=60)

    if addSessionInfo:
        paymentSession = request.session.get(PAYMENT_VALIDATION_STR, {})

        paymentSession.update({
            'invoiceID': str(this_invoice.id),
            'amount': this_total,
            'successUrl': successUrl,
        })
        request.session[PAYMENT_VALIDATION_STR] = paymentSession

    return HttpResponseRedirect(successUrl)


def processPointOfSalePayment(request):
    '''
    This view handles the callbacks from point-of-sale transactions.
    Please note that this will only work if you have set up your callback
    URL in Square to point to this view.
    '''

    # iOS transactions put all response information in the data key:
    data = json.loads(request.GET.get('data', '{}'))
    if data:
        status = data.get('status')
        errorCode = data.get('error_code')
        errorDescription = errorCode

        try:
            stateData = data.get('state', '')
            if stateData:
                metadata = json.loads(b64decode(unquote(stateData).encode()).decode())
            else:
                metadata = {}
        except (TypeError, ValueError, binascii.Error):
            logger.error('Invalid metadata passed from Square app.')
            messages.error(
                request,
                format_html(
                    '<p>{}</p><ul><li><strong>CODE:</strong> {}</li><li><strong>DESCRIPTION:</strong> {}</li></ul>',
                    str(_('ERROR: Error with Square point of sale transaction attempt.')),
                    str(_('Invalid metadata passed from Square app.')),
                )
            )
            return HttpResponseRedirect(reverse('showRegSummary'))

        # This is the normal transaction identifier, which will be stored in the
        # database as a SquarePaymentRecord
        serverTransId = data.get('transaction_id')

        # This is the only identifier passed for non-card transactions.
        clientTransId = data.get('client_transaction_id')
    else:
        # Android transactions use this GET response syntax
        errorCode = request.GET.get('com.squareup.pos.ERROR_CODE')
        errorDescription = request.GET.get('com.squareup.pos.ERROR_DESCRIPTION')
        status = 'ok' if not errorCode else 'error'

        # This is the normal transaction identifier, which will be stored in the
        # database as a SquarePaymentRecord
        serverTransId = request.GET.get('com.squareup.pos.SERVER_TRANSACTION_ID')

        # This is the only identifier passed for non-card transactions.
        clientTransId = request.GET.get('com.squareup.pos.CLIENT_TRANSACTION_ID')

        # Load the metadata, which includes the registration or invoice ids
        try:
            stateData = request.GET.get('com.squareup.pos.REQUEST_METADATA', '')
            if stateData:
                metadata = json.loads(b64decode(unquote(stateData).encode()).decode())
            else:
                metadata = {}

        except (TypeError, ValueError, binascii.Error):
            logger.error('Invalid metadata passed from Square app.')
            messages.error(
                request,
                format_html(
                    '<p>{}</p><ul><li><strong>CODE:</strong> {}</li><li><strong>DESCRIPTION:</strong> {}</li></ul>',
                    str(_('ERROR: Error with Square point of sale transaction attempt.')),
                    str(_('Invalid metadata passed from Square app.')),
                )
            )
            return HttpResponseRedirect(reverse('showRegSummary'))

    # Other things that can be passed in the metadata
    sourceUrl = metadata.get('sourceUrl', reverse('showRegSummary'))
    successUrl = metadata.get('successUrl', reverse('registration'))
    submissionUserId = metadata.get('userId', getattr(getattr(request, 'user', None), 'id', None))
    transactionType = metadata.get('transaction_type')
    taxable = metadata.get('taxable', False)
    addSessionInfo = metadata.get('addSessionInfo', False)
    customerEmail = metadata.get('customerEmail')

    if errorCode or status != 'ok':
        # Return the user to their original page with the error message displayed.
        logger.error(
            'Error with Square point of sale transaction attempt.  ' +
            'CODE: %s; DESCRIPTION: %s' % (errorCode, errorDescription)
        )
        messages.error(
            request,
            format_html(
                '<p>{}</p><ul><li><strong>CODE:</strong> {}</li><li><strong>DESCRIPTION:</strong> {}</li></ul>',
                str(_('ERROR: Error with Square point of sale transaction attempt.')), errorCode, errorDescription
            )
        )
        return HttpResponseRedirect(sourceUrl)

    api_instance = TransactionsApi()
    api_instance.api_client.configuration.access_token = getattr(settings, 'SQUARE_ACCESS_TOKEN', '')
    location_id = getattr(settings, 'SQUARE_LOCATION_ID', '')

    if serverTransId:
        try:
            api_response = api_instance.retrieve_transaction(transaction_id=serverTransId, location_id=location_id)
        except ApiException:
            logger.error('Unable to find Square transaction by server ID.')
            messages.error(request, _('ERROR: Unable to find Square transaction by server ID.'))
            return HttpResponseRedirect(sourceUrl)
        if api_response.errors:
            logger.error('Unable to find Square transaction by server ID: %s' % api_response.errors)
            messages.error(
                request,
                str(_('ERROR: Unable to find Square transaction by server ID:')) +
                api_response.errors
            )
            return HttpResponseRedirect(sourceUrl)
        transaction = api_response.transaction
    elif clientTransId:
        # Try to find the transaction in the 50 most recent transactions
        try:
            api_response = api_instance.list_transactions(location_id=location_id)
        except ApiException:
            logger.error('Unable to find Square transaction by client ID.')
            messages.error(request, _('ERROR: Unable to find Square transaction by client ID.'))
            return HttpResponseRedirect(sourceUrl)
        if api_response.errors:
            logger.error('Unable to find Square transaction by client ID: %s' % api_response.errors)
            messages.error(
                request,
                str(_('ERROR: Unable to find Square transaction by client ID:')) +
                api_response.errors
            )
            return HttpResponseRedirect(sourceUrl)
        transactions_list = [x for x in api_response.transactions if x.client_id == clientTransId]
        if len(transactions_list) == 1:
            transaction = transactions_list[0]
        else:
            logger.error('Returned client transaction ID not found.')
            messages.error(request, _('ERROR: Returned client transaction ID not found.'))
            return HttpResponseRedirect(sourceUrl)
    else:
        logger.error('An unknown error has occurred with Square point of sale transaction attempt.')
        messages.error(request, _(
            'ERROR: An unknown error has occurred with Square point of sale transaction attempt.'
        ))
        return HttpResponseRedirect(sourceUrl)

    # Get total information from the transaction for handling invoice.
    this_total = sum([x.amount_money.amount / 100 for x in transaction.tenders or []]) - \
        sum([x.amount_money.amount / 100 for x in transaction.refunds or []])

    # Parse if a specific submission user is indicated
    submissionUser = None
    if submissionUserId:
        try:
            submissionUser = User.objects.get(id=int(submissionUserId))
        except (ValueError, ObjectDoesNotExist):
            logger.warning('Invalid user passed, submissionUser will not be recorded.')

    if 'invoice' in metadata.keys():
        try:
            this_invoice = Invoice.objects.get(id=int(metadata.get('invoice')))
            this_description = _('Invoice Payment: %s' % this_invoice.id)

            if this_invoice.status == Invoice.PaymentStatus.preliminary:
                this_invoice.expirationDate = timezone.now() + timedelta(
                    minutes=getConstant('registration__sessionExpiryMinutes')
                )
            this_invoice.status = Invoice.PaymentStatus.unpaid
            this_invoice.save()

        except (ValueError, TypeError, ObjectDoesNotExist):
            logger.error('Invalid invoice ID passed: %s' % metadata.get('invoice'))
            messages.error(
                request,
                str(_('ERROR: Invalid invoice ID passed')) + ': %s' % metadata.get('invoice')
            )
            return HttpResponseRedirect(sourceUrl)
    else:
        # Gift certificates automatically get a nicer invoice description
        if transactionType == 'Gift Certificate':
            this_description = _('Gift Certificate Purchase')
        else:
            this_description = transactionType
        this_invoice = Invoice.create_from_item(
            this_total,
            this_description,
            submissionUser=submissionUser,
            calculate_taxes=(taxable is not False),
            transactionType=transactionType,
            status=Invoice.PaymentStatus.unpaid,
        )

    paymentRecord, created = SquarePaymentRecord.objects.get_or_create(
        transactionId=transaction.id,
        locationId=transaction.location_id,
        defaults={'invoice': this_invoice, }
    )
    if created:
        # We process the payment now, and enqueue the job to retrieve the
        # transaction again once fees have been calculated by Square
        this_invoice.processPayment(
            amount=this_total,
            fees=0,
            paidOnline=True,
            methodName='Square Point of Sale',
            methodTxn=transaction.id,
            notify=customerEmail,
        )
    updateSquareFees.schedule(args=(paymentRecord, ), delay=60)

    if addSessionInfo:
        paymentSession = request.session.get(PAYMENT_VALIDATION_STR, {})

        paymentSession.update({
            'invoiceID': str(this_invoice.id),
            'amount': this_total,
            'successUrl': successUrl,
        })
        request.session[PAYMENT_VALIDATION_STR] = paymentSession

    return HttpResponseRedirect(successUrl)
