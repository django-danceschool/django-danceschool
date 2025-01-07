from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from cms.models.pluginmodel import CMSPlugin
from cms.models.fields import PageField

import logging
import uuid

from danceschool.core.models import PaymentRecord
from .tasks import updateSquareFees
from .api_client import api_client, iso_timestamp_to_localtime


# Define logger for this file
logger = logging.getLogger(__name__)


class SquarePaymentRecord(PaymentRecord):
    '''
    Keeps a local record of Square transactions so that they can be looked up
    using the REST API.
    '''

    paymentId = models.CharField(
        _('Square Payment ID'), max_length=100, unique=True
    )
    orderId = models.CharField(
        _('Square Order ID'), max_length=100, unique=True, null=True,
        db_column='transactionId',
    )
    locationId = models.CharField(_('Square Location ID'), max_length=100)
    payerEmail = models.EmailField(_('Associated email'), null=True, blank=True)

    data = models.JSONField(_('Additional data'), default=dict, blank=True)

    @property
    def methodName(self):
        return 'Square Checkout'

    @property
    def refundable(self):
        return True

    @property
    def recordId(self):
        '''
        Payment methods should override this if they keep their own unique identifiers.
        '''
        return self.paymentId

    @property
    def netAmountPaid(self):
        payment = self.getPayment()
        return (
            payment.get('amount_money', {}).get('amount', 0) / 100 -
            payment.get('refunded_money', {}).get('amount', 0) / 100
        )

    @property
    def netRefund(self):
        payment = self.getPayment()
        return (
            payment.get('refunded_money', {}).get('amount', 0) / 100
        )

    @property
    def netFees(self):
        payment = self.getPayment()
        refunds = self.getRefunds(payment=payment)

        fees = sum([
            x.get('amount_money', {}).get('amount', 0) / 100
            for x in payment.get('processing_fee', [])
        ])

        for r in refunds:
            fees += sum([
                f.get('amount_money', {}).get('amount', 0) / 100
                for f in r.get('processing_fee', [])
            ])

        return fees

    @property
    def netRevenue(self):
        return self.netAmountPaid - self.netFees

    @property
    def apiPaymentCreated(self):
        return iso_timestamp_to_localtime(
            self.data.get('apiPaymentResponse', {}).get('created_at')
        )

    @property
    def apiPaymentModified(self):
        return iso_timestamp_to_localtime(
            self.data.get('apiPaymentResponse', {}).get('updated_at')
        )

    @property
    def receiptNumber(self):
        return self.data.get('apiPaymentResponse', {}).get('receipt_number')

    @property
    def receiptUrl(self):
        return self.data.get('apiPaymentResponse', {}).get('receipt_url')

    def getClient(self):
        return api_client

    def getPayment(
        self, client=None, use_cache=True, update_cache=True, commit=True
    ):

        cached = self.data.get('apiPaymentResponse', None)
        if use_cache and cached is not None:
                return cached

        if not client:
            client = self.client

        response = client.payments.get_payment(self.paymentId).body.get('payment', {})

        if (update_cache is True) and (response != cached):
            self.data['apiPaymentResponse'] = response
            self.data['apiPaymentResponseDate'] = timezone.localtime().isoformat()
            if commit:
                self.save()
        return response

    def getRefunds(
            self, client=None, use_cache=True, update_cache=True, payment=None,
            commit=True
    ):

        cached = self.data.get('apiRefundResponse', None)
        if use_cache and cached is not None:
                return cached

        if not client:
            client = self.client

        if not payment:
            payment = self.getPayment(client, use_cache, update_cache, commit)

        response = []

        if payment.get('refund_ids', []):
            for y in payment['refund_ids']:
                refund_response = client.refunds.get_payment_refund(y)
                if refund_response.is_error():
                    continue
                r = refund_response.body.get('refund', {})
                if r:
                    response.append(r)

        if update_cache and response != cached:
            self.data['apiRefundResponse'] = response
            self.data['apiRefundResponseDate'] = timezone.localtime().isoformat()
            if commit:
                self.save()
        return response

    def getPayerEmail(self):
        return self.payerEmail

    def refund(self, amount=None):
        # Start by ensuring that we have the most recent information on the
        # payment and what remains to be refunded.
        payment = self.getPayment(use_cache=False, commit=False)
        if not payment:
            return {
                'status': 'error', 'errors': [
                    {'code': 'no_payment', 'message': _('Unable to retrieve Square payment from record.')},
                ]
            }

        # SquarePaymentRecords used to potentially reference multiple tenders,
        # but they are now associated with a single payment that can be refunded
        # up to the allowable amount directly.
        amount_remaining = (
            payment.get('amount_money', {}).get('amount', 0) / 100 -
            payment.get('refunded_money', {}).get('amount', 0) / 100
        )

        if amount:
            amount_to_refund = min(amount, amount_remaining)
        else:
            amount_to_refund = amount_remaining

        refundData = []
        idempotency_key = str(uuid.uuid1())

        body = {
            'idempotency_key': idempotency_key,
            'payment_id': payment.get('id'),
            'amount_money': {
                'amount': int(amount_to_refund * 100),
                'currency': payment.get('amount_money', {}).get('currency')
            }
        }

        response = self.client.refunds.refund_payment(body)
        if response.is_error():
            logger.error('Error in providing Square refund: %s' % response.errors)
            refundData.append({'status': 'error', 'errors': response.errors})
        else:
            this_refund = response.body.get('refund', {})

            # Note that fees are often 0 or missing here, but we enqueue the task
            # retrieve and update them afterward.
            refundData.append({
                'status': 'success',
                'refund_id': this_refund.get('id'),
                'refundAmount': float(this_refund.get('amount_money', {}).get('amount', 0)) / 100,
                'fees': float(this_refund.get('app_fee_money', {}).get('amount', 0)) / 100,
            })

            # Once the refund process is complete, fees will be calculated,
            # so schedule a task to get them and update records one minute
            # in the future.
            updateSquareFees.schedule(args=(self, ), delay=60)

        return refundData

    def __init__(self, *args, **kwargs):
        client = kwargs.pop('client', None)
        super().__init__(*args, **kwargs)
        self.client = client or self.getClient()

    class Meta:
        permissions = (
            ('handle_pos_payments', _('Has access to point-of-sale payment functionality')),
        )
        verbose_name = _('Square payment record')
        verbose_name_plural = _('Payment records')


class SquareCheckoutFormModel(CMSPlugin):
    ''' This model holds options for instances of the SquarePaymentFormPlugin '''

    successPage = PageField(
        verbose_name=_('Success Page'),
        help_text=_(
            'When the user returns to the site after a successful ' +
            'transaction, send them to this page.'
        ),
        related_name='successPageForSquare', null=True, blank=True
    )
    defaultAmount = models.FloatField(
        verbose_name=_('Default amount'),
        help_text=_('The initial value for gift certificate forms.'),
        default=0
    )

    def get_short_description(self):
        return self.plugin_type or self.id
