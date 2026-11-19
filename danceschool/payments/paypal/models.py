from django.db import models
from django.utils.translation import gettext_lazy as _

from cms.models.pluginmodel import CMSPlugin
from cms.models.fields import PageField

import logging
import uuid

from paypalserversdk.exceptions.api_exception import ApiException
from paypalserversdk.models.money import Money
from paypalserversdk.models.refund_request import RefundRequest

from danceschool.core.models import PaymentRecord
from danceschool.core.constants import getConstant

from . import api_client


# Define logger for this file
logger = logging.getLogger(__name__)


class PaypalPaymentRecord(PaymentRecord):
    '''
    Keeps a local record of Paypal transactions so that they can be looked up
    using the REST API.  paymentId is the id of the PayPal order, and
    captureId is the id of the payment once it has been captured.  Records
    of payments made with PayPal's older v1 Payments API have a paymentId
    beginning with "PAY-" and no captureId; they can no longer be looked up
    or refunded from this site.
    '''

    paymentId = models.CharField(_('Paypal Payment ID'), max_length=50, unique=True)
    payerId = models.CharField(_('Paypal Payer ID'), max_length=50, null=True, blank=True)
    status = models.CharField(_('Current status'), max_length=30, null=True, blank=True)
    captureId = models.CharField(_('Paypal Capture ID'), max_length=50, null=True, blank=True)

    @property
    def methodName(self):
        return 'Paypal Express Checkout'

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
    def legacy(self):
        ''' A payment made with PayPal's older v1 Payments API. '''
        return (self.paymentId or '').startswith('PAY-')

    @property
    def api_error(self):
        ''' Why the details of this payment could not be retrieved, if they could not. '''
        if self.legacy:
            return str(_(
                'this payment was made with an older PayPal integration, so it ' +
                'must be looked up and refunded in your PayPal account'
            ))
        return getattr(self, '_api_error', None)

    def getOrder(self):
        ''' The PayPal order for this payment, or None if it cannot be retrieved. '''
        if self.legacy:
            return None
        try:
            return api_client.get_client().orders.get_order({'id': self.paymentId}).body
        except ApiException as e:
            self._api_error = api_client.error_message(e)
            logger.error('Unable to retrieve PayPal order %s: %s' % (self.paymentId, self._api_error))
            return None

    @property
    def netAmountPaid(self):
        order = self.getOrder()
        if not order:
            return None
        payments = order.purchase_units[0].payments
        captured = sum([
            float(x.amount.value) for x in (getattr(payments, 'captures', None) or [])
            if x.status == 'COMPLETED'
        ])
        refunded = sum([
            float(x.amount.value) for x in (getattr(payments, 'refunds', None) or [])
            if x.status in ['COMPLETED', 'PENDING']
        ])
        return captured - refunded

    def getPayerEmail(self):
        order = self.getOrder()
        payer = getattr(order, 'payer', None)
        return getattr(payer, 'email_address', None)

    def refund(self, amount=None):
        if self.legacy or not self.captureId:
            return [{'status': 'error', 'errors': [{
                'code': 'not_refundable',
                'message': str(_('No refund was attempted: %s.') % (
                    self.api_error or _('this payment was never captured')
                )),
            }]}]

        body = RefundRequest()
        if amount is not None:
            body = RefundRequest(amount=Money(
                currency_code=getConstant('general__currencyCode'),
                value='%.2f' % amount,
            ))

        try:
            refund = api_client.get_client().payments.refund_captured_payment({
                'capture_id': self.captureId,
                'body': body,
                # Ensures that the same refund is not made twice if the
                # request is retried.
                'paypal_request_id': str(uuid.uuid4()),
                'prefer': 'return=representation',
            }).body
        except ApiException as e:
            message = api_client.error_message(e)
            logger.error('Error processing PayPal refund: %s' % message)
            return [{'status': 'error', 'errors': [{'code': 'paypal_error', 'message': message}]}]

        if refund.status not in ['COMPLETED', 'PENDING']:
            logger.error('PayPal refund %s has status %s.' % (refund.id, refund.status))
            return [{'status': 'error', 'errors': [{
                'code': refund.status,
                'message': str(_('PayPal reported the refund as %s') % refund.status),
            }]}]

        logger.info('Refund successfully processed.')

        # PayPal returns part of its fee when a payment is refunded, so the
        # fees on the invoice go down by that amount.
        breakdown = getattr(refund, 'seller_payable_breakdown', None)
        fee = getattr(breakdown, 'paypal_fee', None)
        return [{
            'status': 'success',
            'refund_id': refund.id,
            'refundAmount': float(refund.amount.value),
            'fees': -1 * float(fee.value) if fee else 0,
        }]

    class Meta:
        verbose_name = _('Paypal payment record')
        verbose_name_plural = _('Payment records')


class PayNowFormModel(CMSPlugin):
    ''' This model holds options for instances of the GiftCertificateFormPlugin and the CartPaymentFormPlugin '''

    successPage = PageField(
        verbose_name=_('Success Page'),
        help_text=_(
            'When the user returns to the site after a successful ' +
            'transaction, send them to this page.'
        ),
        related_name='successPageFor'
    )
    defaultAmount = models.FloatField(
        verbose_name=_('Default amount'),
        help_text=_('The initial value for gift certificate forms.'),
        default=0
    )

    def get_short_description(self):
        return self.plugin_type or self.id
