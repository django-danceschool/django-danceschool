from django.db import models
from django.db.models import CheckConstraint, Q
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from cms.models.pluginmodel import CMSPlugin
from cms.models.fields import PageField

import logging
from square.client import Client
import uuid

from danceschool.core.models import PaymentRecord
from .tasks import updateSquareFees
from .helpers import (
    getClient, getPayments, getRefunds, getNetAmountPaid, getNetFees
)


# Define logger for this file
logger = logging.getLogger(__name__)


class SquarePaymentRecord(PaymentRecord):
    '''
    Keeps a local record of Square transactions so that they can be looked up
    using the REST API.
    '''

    orderId = models.CharField(
        _('Square Order ID'), max_length=100, unique=True, null=True,
        db_column='transactionId',
    )
    paymentId = models.CharField(
        _('Square Payment ID'), max_length=100, unique=True, null=True
    )
    locationId = models.CharField(_('Square Location ID'), max_length=100)
    payerEmail = models.EmailField(_('Associated email'), null=True, blank=True)

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
        return self.paymentId or self.orderId

    @property
    def netAmountPaid(self):
        return getNetAmountPaid(order_id=self.orderId)

    @property
    def netFees(self):
        return getNetFees(order_id=self.orderId)

    @property
    def netRevenue(self):
        return self.netAmountPaid - self.netFees

    def getClient(self):
        return getClient()

    def getPayments(self, client=None):
        if not client:
            client = self.getClient()

        if self.paymentId:
            return [client.payments.get_payment(self.paymentId).body.get('payment', {}),]
        else:
            return getPayments(order_id=self.orderId, client=client)

    def getRefunds(self, client=None):
        return getRefunds(order_id=self.orderId, client=client)

    def getPayerEmail(self):
        return self.payerEmail

    def refund(self, amount=None):
        client = self.getClient()

        payments = self.getPayments(client=client)
        if not payments:
            return {
                'status': 'error', 'errors': [
                    {'code': 'no_payments', 'message': _('Unable to retrieve Square payments from record.')},
                ]

            }

        # For both partial and full refunds, we loop through the tenders and refund
        # them as much as possible until we've refunded all that we want to refund.
        if not amount:
            amount = sum([
                x.get('amount_money', {}).get('amount', 0) / 100 -
                x.get('refunded_money', {}).get('amount', 0) / 100
                for x in payments
            ])

        refundData = []

        remains_to_refund = amount
        tender_index = 0
        while remains_to_refund > 0:
            idempotency_key = str(uuid.uuid1())

            this_tender = payments[tender_index]
            this_tender_remaining = (
                this_tender.get('amount_money', {}).get('amount', 0) / 100 -
                this_tender.get('refunded_money', {}).get('amount', 0) / 100
            )
            
            to_refund = min(this_tender_remaining, remains_to_refund)

            body = {
                'idempotency_key': idempotency_key,
                'payment_id': this_tender.get('id'),
                'amount_money': {
                    'amount': int(to_refund * 100),
                    'currency': this_tender.get('amount_money', {}).get('currency')
                }
            }

            response = client.refunds.refund_payment(body)
            if response.is_error():
                logger.error('Error in providing Square refund: %s' % response.errors)
                refundData.append({'status': 'error', 'errors': response.errors})
                break

            this_refund = response.body.get('refund', {})

            # Note that fees are often 0 or missing here, but we enqueue the task
            # retrieve and update them afterward.
            refundData.append({
                'status': 'success',
                'refund_id': this_refund.get('id'),
                'refundAmount': float(this_refund.get('amount_money', {}).get('amount', 0)) / 100,
                'fees': float(this_refund.get('app_fee_money', {}).get('amount', 0)) / 100,
            })

            remains_to_refund -= to_refund
            tender_index += 1

            # Once the refund process is complete, fees will be calculated,
            # so schedule a task to get them and update records one minute
            # in the future.
            updateSquareFees.schedule(args=(self, ), delay=60)

        return refundData

    class Meta:
        permissions = (
            ('handle_pos_payments', _('Has access to point-of-sale payment functionality')),
        )
        verbose_name = _('Square payment record')
        verbose_name_plural = _('Payment records')
        constraints = (
            CheckConstraint(
                name='order_or_payment_specified',
                check=(Q(orderId__isnull=False) | Q(paymentId__isnull=False))
            ),
        )


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
