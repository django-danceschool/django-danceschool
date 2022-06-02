from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from django.contrib import messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.views.generic import View

import uuid
from square.client import Client
import logging
from datetime import timedelta
import json
from base64 import b64decode
import binascii
from urllib.parse import unquote
from time import sleep

from danceschool.core.models import Invoice
from danceschool.core.constants import getConstant, PAYMENT_VALIDATION_STR
from danceschool.core.helpers import getReturnPage

from .models import SquarePaymentRecord
from .tasks import updateSquareFees


# Define logger for this file
logger = logging.getLogger(__name__)

class ProcessSquarePaymentView(View):
    '''
    This view handles the charging of approved Square Checkout payments.

    All Checkout payments must either be associated with a pre-existing Invoice
    or a registration, or they must have an amount and type passed in the post data
    (such as gift certificate payment requests).
    '''

    def post(self, request, *args, **kwargs):
        logger.info('Received request for Square Checkout payment.')

        try:
            data = json.loads(request.body)
        except json.decoder.JSONDecodeError:
            return HttpResponseBadRequest()

        invoice_id = data.get('invoice_id')
        amount = data.get('amount')
        submissionUserId = data.get('user_id')
        transactionType = data.get('transaction_type')
        taxable = data.get('taxable', False)
        sourceUrl = data.get('sourceUrl', reverse('showRegSummary'))
        addSessionInfo = data.get('addSessionInfo', False)
        customerEmail = data.get('customerEmail')

        # Send users back to the invoice to confirm the successful payment.
        # If none is specified, then return to the registration page.
        successUrl = data.get(
            'successUrl',
            getReturnPage(request.session.get('SITE_HISTORY', {})).get('url')
        )
        if not successUrl:
            successUrl = reverse('registration')

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
                    ),
                    extra_tags='square-error'
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
                    ),
                    extra_tags='square-error'
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
                    )),
                    extra_tags='square-error'
                )
            )
            return HttpResponseRedirect(sourceUrl)

        if this_invoice.status == Invoice.PaymentStatus.preliminary:
            this_invoice.status = Invoice.PaymentStatus.unpaid

        this_currency = getConstant('general__currencyCode')
        this_total = min(this_invoice.outstandingBalance, amount)

        client = Client(
            access_token=getattr(settings, 'SQUARE_ACCESS_TOKEN', ''),
            environment=getattr(settings, 'SQUARE_ENVIRONMENT', 'production'),
        )

        body = {
            'source_id': data.get('sourceId'),
            'location_id': getattr(settings, 'SQUARE_LOCATION_ID', ''),
            'idempotency_key': data.get('idempotency_key', str(uuid.uuid1())),
            'amount_money': {
                'amount': int(100 * this_total),
                'currency': this_currency,
            },
        }

        response = client.payments.create_payment(body)
        if response.is_error():
            logger.error('Error in charging Square transaction: %s' % response.errors)

            this_invoice.status = Invoice.PaymentStatus.error
            this_invoice.save()
            errors_string = ''
            for err in response.errors:
                errors_string += '<li><strong>CODE:</strong> %s, %s</li>' % (
                    err.get('code', str(_('Unknown'))), err.get('detail', str(_('Unknown')))
                )
            messages.error(
                request,
                format_html(
                    '<p>{}</p><ul>{}</ul>',
                    str(_('ERROR: Error with Square checkout transaction attempt.')),
                    mark_safe(response.errors),
                ),
                extra_tags='square-error'
            )
            return HttpResponseRedirect(sourceUrl)
        else:
            logger.info('Square charge successfully created.')

        payment = response.body.get('payment')

        paymentRecord = SquarePaymentRecord.objects.create(
            invoice=this_invoice,
            orderId=payment.get('order_id'),
            paymentId=payment.get('id'),
            locationId=payment.get('location_id'),
        )

        # We process the payment now, and enqueue the job to retrieve the
        # transaction again once fees have been calculated by Square
        this_invoice.processPayment(
            amount=this_total,
            fees=0,
            paidOnline=True,
            methodName='Square Checkout',
            methodTxn=payment.get('id'),
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


class ProcessPointOfSalePaymentView(View):
    '''
    This view handles the callbacks from point-of-sale transactions.
    Please note that this will only work if you have set up your callback
    URL in Square to point to this view.
    '''

    def getPayment(self, request, serverTransId=None, clientTransId=None):

        logger.debug(f'Received callback with identifiers. Server: {serverTransId} Client: {clientTransId}')

        if not serverTransId and not clientTransId:
            logger.error('An unknown error has occurred with Square point of sale transaction attempt.')
            messages.error(
                self.request,
                _('ERROR: An unknown error has occurred with Square point of sale transaction attempt.'),
                extra_tags='square-error'
            )
            return

        location_id = getattr(settings, 'SQUARE_LOCATION_ID', '')
        client = Client(
            access_token=getattr(settings, 'SQUARE_ACCESS_TOKEN', ''),
            environment=getattr(settings, 'SQUARE_ENVIRONMENT', 'production'),   
        )

        payment = None

        if serverTransId:
            # Added to avoid errors associated with Square API not being up to date.
            sleep(1)
            response = client.transactions.retrieve_transaction(
                transaction_id=serverTransId, location_id=location_id
            )
            response_key = 'transaction'
            if response.is_error():
                response = client.orders.retrieve_order(serverTransId)
                response_key = 'order'

            if response.is_error():
                logger.error('Unable to find Square transaction for %s by server ID: %s' % (
                    serverTransId, response.errors
                ))
                messages.error(
                    request,
                    str(_('ERROR: Unable to find Square transaction for {} by server ID: '.format(serverTransId))) +
                    str(response.errors),
                    extra_tags='square-error'
                )
            else:
                payment_list = [x.get('id') for x in response.body.get(response_key, {}).get('tenders', [])]
                if len(payment_list) == 1:
                    payment = client.payments.get_payment(payment_list[0]).body.get('payment')
                    logger.debug(f'Successfully retrieved payment based on server transaction identifier {serverTransId}')
                else:
                    logger.error('Returned client transaction ID not found.')
                    messages.error(
                        request, _('ERROR: Returned client transaction ID not found.'),
                        extra_tags='square-error'
                    )

        if clientTransId and not payment:
            # Try to find the payment in the 50 most recent payments
            response = client.payments.list_payments(location_id=location_id)
            if response.is_error():
                logger.error('Unable to find Square transaction for %s by client ID: %s' % (
                    location_id, response.errors
                ))
                messages.error(
                    request,
                    str(_('ERROR: Unable to find Square transaction by client ID:' )) +
                    str(response.errors),
                    extra_tags='square-error'
                )
            else:
                payment_list = [x for x in response.body.get('payments', []) if x.get('order_id') == clientTransId]
                if len(payment_list) == 1:
                    payment = payment_list[0].body.get('payment')
                    logger.debug(f'Successfully retrieved payment based on client transaction identifier {clientTransId}')
                else:
                    logger.error('Returned client transaction ID not found.')
                    messages.error(
                        request, _('ERROR: Returned client transaction ID not found.'),
                        extra_tags='square-error'
                    )

        return payment


    def get(self, request, *args, **kwargs):
        # iOS transactions put all response information in the data key:
        data = json.loads(request.GET.get('data', '{}'))
        if data:
            logger.debug(f'Square Point-of-sale request data: {data}')
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
                    ),
                    extra_tags='square-error'
                )
                return HttpResponseRedirect(reverse('showRegSummary'))

            # This is the normal transaction identifier, which will be stored in the
            # database as a SquarePaymentRecord
            serverTransId = data.get('transaction_id')

            # This is the only identifier passed for non-card transactions.
            clientTransId = data.get('client_transaction_id')
        else:
            logger.debug(f'Square Point-of-sale request GET: {request.GET}')
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
                    ),
                    extra_tags='square-error'
                )
                return HttpResponseRedirect(reverse('showRegSummary'))

        # Other things that can be passed in the metadata
        sourceUrl = metadata.get('sourceUrl', reverse('showRegSummary'))
        submissionUserId = metadata.get('userId', getattr(getattr(request, 'user', None), 'id', None))
        transactionType = metadata.get('transaction_type')
        taxable = metadata.get('taxable', False)
        addSessionInfo = metadata.get('addSessionInfo', False)
        customerEmail = metadata.get('customerEmail')

        # Send users back to the invoice to confirm the successful payment.
        # If none is specified, then return to the registration page.
        successUrl = (
            getReturnPage(request.session.get('SITE_HISTORY', {})).get('url') or
            metadata.get('successUrl') or
            reverse('registration')
        )

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
                ),
                extra_tags='square-error'
            )
            return HttpResponseRedirect(sourceUrl)

        # Use the Square API to get the payment based on the passed identifiers.
        payment = self.getPayment(request, serverTransId, clientTransId)
        if not payment:
            return HttpResponseRedirect(sourceUrl)

        # Get total information from the transaction for handling invoice.
        this_total = (
            payment.get('amount_money', {}).get('amount', 0) / 100 -
            payment.get('refunded_money', {}).get('amount', 0) / 100
        )

        # Parse if a specific submission user is indicated
        submissionUser = None
        if submissionUserId:
            try:
                submissionUser = User.objects.get(id=int(submissionUserId))
            except (ValueError, ObjectDoesNotExist):
                logger.warning('Invalid user passed, submissionUser will not be recorded.')

        if 'invoice' in metadata.keys():
            try:
                this_invoice = Invoice.objects.get(id=metadata.get('invoice'))
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
                    str(_('ERROR: Invalid invoice ID passed')) + ': %s' % metadata.get('invoice'),
                    extra_tags='square-error'
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
            paymentId=payment.get('id'), orderId=payment.get('order_id'),
            locationId=payment.get('location_id'),
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
                methodTxn=payment.get('id'),
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
