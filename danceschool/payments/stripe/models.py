from django.db import models
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from cms.models.pluginmodel import CMSPlugin
from cms.models.fields import PageField

import logging

from danceschool.core.models import PaymentRecord


# Define logger for this file
logger = logging.getLogger(__name__)


class StripeCharge(PaymentRecord):

    def __init__(self, *args, **kwargs):
        super(StripeCharge, self).__init__(*args, **kwargs)

        # bring in stripe, and get the api key from settings.py
        import stripe
        stripe.api_key = getattr(settings,'STRIPE_PRIVATE_KEY','')

        self.stripe = stripe

    # store the stripe charge id for this sale
    chargeId = models.CharField(_('Charge Id'),max_length=32)
    status = models.CharField(_('Current status'),max_length=30,null=True,blank=True)

    @property
    def methodName(self):
        return 'Stripe Charge'

    @property
    def recordId(self):
        return self.chargeId

    @property
    def netAmountPaid(self):
        charge = self.getCharge()
        return float(charge.amount - charge.amount_refunded) / 100

    @property
    def refundable(self):
        return True

    def getCharge(self):
        return self.stripe.Charge.retrieve(self.chargeId)

    def getPayerEmail(self):
        charge = self.getCharge()
        customer = self.stripe.Customer.retrieve(charge.customer)
        return customer.email

    def refund(self, amount=None):
        refundData = []

        refund_kwargs = {
            'charge': self.chargeId,
            'reason': 'requested_by_customer',
        }
        if amount:
            refund_kwargs['amount'] = int(amount * 100)

        refund = self.stripe.Refund.create(**refund_kwargs)

        if refund.status == 'succeeded':
            bt = self.stripe.BalanceTransaction.retrieve(refund.balance_transaction)
            refundData.append({
                'status': 'success',
                'refund_id': refund.id,
                'refundAmount': float(refund.amount) / 100,
                'fees': float(bt.fee) / 100,
            })
        else:
            logger.error('Error processing refund.')
            refundData.append({'status': 'error', 'errors': refund.status})

        return refundData

    class Meta:
        verbose_name = _('Stripe charge')
        verbose_name_plural = _('Stripe charges')


class StripeChargeFormModel(CMSPlugin):
    ''' This model holds options for instances of the GiftCertificateFormPlugin and the CartPaymentFormPlugin '''

    successPage = PageField(verbose_name=_('Success Page'),help_text=_('When the user returns to the site after a successful transaction, send them to this page.'),related_name='successPageForStripe')
    defaultAmount = models.FloatField(verbose_name=_('Default amount'),help_text=_('The initial value for gift certificate forms.'),default=0)

    def get_short_description(self):
        return self.plugin_type or self.id
