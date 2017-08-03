from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from django.core.validators import MinValueValidator

import logging

from danceschool.core.models import PaymentRecord


# Define logger for this file
logger = logging.getLogger(__name__)


@python_2_unicode_compatible
class PaypalHereRecord(PaymentRecord):
    '''
    Point of Sale payments using the Paypal Here system are stored here
    '''

    paypalInvoiceId = models.CharField(_('Paypal Invoice ID'),max_length=50,unique=True)
    paymentType = models.CharField(_('Transaction Type'),max_length=50,null=True,blank=True)
    txId = models.CharField(_('Merchant Tax ID'),max_length=50,null=True,blank=True)
    total = models.FloatField(_('Amount paid'),validators=[MinValueValidator(0),])
    payerEmail = models.EmailField(_('Payer email'),null=True,blank=True)

    @property
    def methodName(self):
        return 'Paypal Here (POS)'

    @property
    def refundable(self):
        return False

    @property
    def recordId(self):
        '''
        Payment methods should override this if they keep their own unique identifiers.
        '''
        return self.paypalInvoiceId

    @property
    def netAmountPaid(self):
        return self.grandTotal

    def getPayerEmail(self):
        return self.payerEmail

    class Meta:
        verbose_name = _('Paypal Here payment record')
        verbose_name_plural = _('Paypal Here payment records')
        permissions = (
            ('process_paypal_here_payments',_('Can process point-of-sale payments using Paypal Here')),
        )
