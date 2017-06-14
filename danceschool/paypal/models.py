from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

from cms.models.pluginmodel import CMSPlugin
from cms.models.fields import PageField

import logging
from paypalrestsdk import Payment, Sale

from danceschool.core.models import Invoice
from danceschool.core.constants import getConstant


# Define logger for this file
logger = logging.getLogger(__name__)


@python_2_unicode_compatible
class PaymentRecord(models.Model):
    '''
    Keeps a local record of Paypal transactions so that they can be looked up
    using the REST API.
    '''

    paymentId = models.CharField(_('Paypal Payment ID'),max_length=50,unique=True)
    payerId = models.CharField(_('Paypal Payer ID'),max_length=50,null=True,blank=True)
    invoice = models.ForeignKey(Invoice, verbose_name=_('Invoice'), null=True,blank=True, related_name='paypalpayments')
    status = models.CharField(_('Current status'),max_length=30,null=True,blank=True)

    creationDate = models.DateTimeField(_('Created'),auto_now_add=True)
    modifiedDate = models.DateTimeField(_('Last updated'),auto_now=True)

    def getPayment(self):
        return Payment.find(self.paymentId)

    def getSaleIds(self):
        ids = []
        payment = self.getPayment()
        for t in payment.transactions:
            for r in t.related_resources:
                if hasattr(r,'sale') and r.sale:
                    ids.append(r.sale.id)
        return ids

    def getRefundIds(self):
        ids = []
        payment = self.getPayment()
        for t in payment.transactions:
            for r in t.related_resources:
                if hasattr(r,'refund') and r.refund:
                    ids.append(r.refund.id)
        return ids

    def getNetAmountPaid(self):
        payment = self.getPayment()
        return sum([float(t.amount.total) for t in payment.transactions])

    def refund(self, amount=None):
        saleIds = self.getSaleIds()
        refundData = []

        leftToRefund = amount or 0
        for this_id in saleIds:
            # No need to continue if the full amount requested has been refunded
            if amount is not None and leftToRefund <= 0:
                break

            this_sale = Sale.find(this_id)

            if amount is not None:
                this_amount = min(float(this_sale.amount.total), leftToRefund)

                refund = this_sale.refund({
                    'amount': {
                        'total': '{0:.2f}'.format(this_amount),
                        'currency': getConstant('general__currencyCode'),
                    }
                })
            else:
                refund = this_sale.refund()

            if refund.success():
                logger.info('Refund successfully processed.')

                refundData.append({
                    'status': 'success',
                    'refund_id': refund.id,
                    'sale_id': refund.sale_id,
                    'refundAmount': float(refund.amount.total),

                    # This is (annoyingly) hard-coded for now because the Paypal REST API does
                    # not yet report fees in the event of a refund.  Hopefully this can be removed
                    # soon.
                    'fees': -1 * (
                        (float(this_sale.transaction_fee.value) - getConstant('paypal__fixedTransactionFee')) *
                        (float(refund.amount.total) / float(this_sale.amount.total))
                    ),
                })
                leftToRefund -= this_amount
            else:
                logger.error('Error processing refund.')
                refundData.append({'status': 'error', 'errors': refund.error})

        return refundData


class PayNowFormModel(CMSPlugin):
    ''' This model holds options for instances of the GiftCertificateFormPlugin and the CartPaymentFormPlugin '''

    successPage = PageField(verbose_name=_('Success Page'),help_text=_('When the user returns to the site after a successful transaction, send them to this page.'),related_name='successPageFor')
    defaultAmount = models.FloatField(verbose_name=_('Default amount'),help_text=_('The initial value for gift certificate forms.'),default=0)
