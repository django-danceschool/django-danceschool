from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _

from polymorphic.models import PolymorphicModel
import logging

from .invoices import Invoice

logger = logging.getLogger(__name__)


class PaymentRecord(PolymorphicModel):
    '''
    All payments to invoices should be recorded using PaymentRecords.  Individual payment
    processors should be subclassed from this base class. Since this is a polymorphic model,
    invoice operations can easily get a list of all payments by querying this model, but can
    still perform operations on individual payment types depending on their features.  The
    only payment method that is enabled by default is the 'Cash' payment method.
    '''

    invoice = models.ForeignKey(
        Invoice, verbose_name=_('Invoice'), null=True, blank=True, on_delete=models.SET_NULL
    )

    creationDate = models.DateTimeField(_('Created'), auto_now_add=True)
    modifiedDate = models.DateTimeField(_('Last updated'), auto_now=True)

    submissionUser = models.ForeignKey(
        User, verbose_name=_('Submission user'), null=True, blank=True,
        related_name='payments_submitted', on_delete=models.SET_NULL
    )

    @property
    def refundable(self):
        '''
        Payment methods that can be automatically refunded should override this to return True.
        '''
        return False

    @property
    def methodName(self):
        '''
        Payment methods should override this with a descriptive name.
        '''
        return None

    @property
    def recordId(self):
        '''
        Payment methods should override this if they keep their own unique identifiers.
        '''
        return self.id

    @property
    def netAmountPaid(self):
        '''
        This method should also be overridden by individual payment methods.
        '''
        return None

    def getPayerEmail(self):
        '''
        This method should be overridden by individual payment methods.
        '''
        return None

    def refund(self, amount):
        '''
        This method should be overridden by individual payment methods to process refunds.
        '''
        return False

    class Meta:
        ordering = ('-modifiedDate',)
        verbose_name = _('Payment record')
        verbose_name_plural = _('Payment records')


class CashPaymentRecord(PaymentRecord):
    '''
    This subclass of PaymentRecord is actually a catch-all that can be used for cash payments,
    checks, or other non-electronic or electronic methods of payment that do not have their own
    payment processor app.
    '''

    class PaymentStatus(models.TextChoices):
        needsCollection = ('N', _('Cash payment recorded, needs collection'))
        collected = ('C', _('Cash payment collected'))
        fullRefund = ('R', _('Refunded in full'))

    amount = models.FloatField(_('Amount paid'), validators=[MinValueValidator(0), ])
    refundAmount = models.FloatField(
        _('Amount refunded'), default=0, validators=[MinValueValidator(0), ]
    )

    payerEmail = models.EmailField(_('Payer email'), null=True, blank=True)

    status = models.CharField(
        _('Payment status'), max_length=1, choices=PaymentStatus.choices,
        default=PaymentStatus.needsCollection
    )
    collectedByUser = models.ForeignKey(
        User, null=True, blank=True, verbose_name=_('Collected by user'),
        related_name='collectedcashpayments', on_delete=models.SET_NULL
    )
    paymentMethod = models.CharField(
        _('Payment method'), max_length=30, default='Cash'
    )

    @property
    def methodName(self):
        return self.paymentMethod

    @property
    def netAmountPaid(self):
        return self.amount - self.refundAmount

    @property
    def refundable(self):
        return True

    def getPayerEmail(self):
        return self.payerEmail

    def refund(self, amount=None):
        '''
        This method keeps track of the amount refunded, but it cannot enforce
        that the cash is actually handed back.
        '''

        if not amount:
            amount = self.netAmountPaid

        self.refundAmount += amount
        self.save()

        return [{
            'status': 'success',
            'refundAmount': amount,
            'fees': 0,
        }]

    class Meta:
        verbose_name = _('Cash payment record')
        verbose_name_plural = _('Cash payment records')
