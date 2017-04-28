from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

from cms.models.pluginmodel import CMSPlugin
from cms.models.fields import PageField

import logging

from danceschool.core.models import TemporaryRegistration, Registration, Event
from danceschool.core.constants import getConstant
from danceschool.financial.models import RevenueItem, RevenueCategory
from danceschool.financial.constants import PAYPAL_PAYMENTMETHOD_ID


# Define logger for this file
logger = logging.getLogger(__name__)


@python_2_unicode_compatible
class Invoice(models.Model):
    '''
    When a Paypal invoice is created
    '''
    invoiceNumber = models.CharField(verbose_name=_('Internal Invoice Number'),max_length=100,unique=True)
    paypalInvoiceID = models.CharField(verbose_name=_('Paypal Invoice ID'),max_length=100,unique=True)

    creationDate = models.DateTimeField(auto_now_add=True)
    paymentDate = models.DateTimeField(null=True,blank=True)

    invoiceURL = models.URLField(verbose_name=_('Invoice View URL'),null=True,blank=True)
    payerViewURL = models.URLField(verbose_name=_('Invoice Payment URL'),null=True,blank=True)

    totalAmount = models.FloatField(verbose_name=_('Invoice Total Amount (net of discounts)'))

    # Eventually this should be converted to a JSONField (needs PostGreSQL)
    itemList = models.TextField(verbose_name=_('Item List Passed to Invoice'),null=True,blank=True)

    def __str__(self):
        return self.paypalInvoiceID + " " + self.invoiceNumber + ": " + self.creationDate.strftime('%Y-%m-%d %H:%M:%S')


@python_2_unicode_compatible
class IPNMessage(models.Model):
    '''
    Paypal sends IPN messages when a payment is made.
    '''
    message = models.TextField(null=True,blank=True)
    registration = models.ForeignKey(TemporaryRegistration,verbose_name=_('Initial Temporary Registration'), null=True)
    finalRegistration = models.OneToOneField(Registration,verbose_name=_('Final Registration'),null=True)
    priorTransaction = models.ForeignKey('self',related_name='subsequenttransactions',null=True)
    paypalInvoice = models.ForeignKey(Invoice,verbose_name=_('Paypal-Submitted Invoice'),null=True)

    invoice = models.CharField(max_length=80,verbose_name=_('Invoice number'))
    generated_invoice = models.CharField(max_length=100,verbose_name=_('Paypal-generated invoice number'),null=True,blank=True)
    mc_fee = models.FloatField()
    mc_gross = models.FloatField()
    payment_status = models.CharField(max_length=30)
    payment_date = models.DateTimeField()
    txn_id = models.CharField(max_length=30,unique=True)
    txn_type = models.CharField(max_length=30)
    custom = models.TextField()
    mc_currency = models.CharField(max_length=30)
    payer_email = models.EmailField()
    receiver_email = models.EmailField()
    payer_id = models.CharField(max_length=30)

    @property
    def netRevenue(self):
        if self.priorTransaction:
            return self.priorTransaction.netRevenue
        else:
            refunds = sum([x.mc_gross - x.mc_fee for x in self.subsequenttransactions.all()])
            return self.mc_gross - self.mc_fee + refunds

    @property
    def totalFees(self):
        if self.priorTransaction:
            return self.priorTransaction.totalFees
        else:
            return sum([x.mc_fee for x in self.subsequenttransactions.all()])

    @property
    def initialTransaction(self):
        if self.priorTransaction:
            return self.priorTransaction
        else:
            return self

    @property
    def relatedTransactions(self):
        return IPNMessage.objects.filter(Q(txn_id=self.txn_id) | Q(priorTransaction=self) | Q(subsequenttransactions=self))

    @property
    def totalReceived(self):
        return sum([x.mc_gross - x.mc_fee for x in self.relatedTransactions.filter(payment_status='Completed')])

    @property
    def totalRefunded(self):
        return -1 * sum([x.mc_gross for x in self.relatedTransactions.filter(payment_status='Refunded')])

    @property
    def unallocatedRefunds(self):
        return self.totalRefunded - sum([x.totalRefunds for x in self.ipncartitem_set.all()])

    def __str__(self):
        return self.invoice + " " + self.payer_email + " " + self.registration.__str__()

    def clean(self):
        # Non-initial transactions cannot also have subsequent transactions.
        if self.priorTransaction and self.subsequenttransactions.all():
            raise ValidationError(_('IPN cannot have both a prior transaction and subsequent transactions.'))

    class Meta:
        verbose_name = _('Paypal IPN message')

        # Add custom permission required to submit invoices
        permissions = (
            ("allocate_refunds",_("Can allocate Paypal refunds to individual registration items")),
        )


class IPNCartItem(models.Model):
    ipn = models.ForeignKey(IPNMessage)
    revenueItem = models.ForeignKey(RevenueItem,null=True,blank=True)

    invoiceName = models.CharField(_('Invoice Item Name'), max_length=100,null=True,blank=True)
    invoiceNumber = models.CharField(_('Invoice Item Number'),max_length=50)
    mc_gross = models.FloatField(_('Gross Amount'),default=0)

    refundAmount = models.FloatField(_('Allocated Refund Amount'),default=0)

    @property
    def initialCartItem(self):
        if self.ipn.priorTransaction:
            return self.ipn.initialTransaction.ipncartitem_set.get(invoiceNumber=self.invoiceNumber)
        else:
            return self

    @property
    def relatedCartItems(self):
        return IPNCartItem.objects.filter(invoiceNumber=self.invoiceNumber).filter(Q(ipn__txn_id=self.ipn.txn_id) | Q(ipn__priorTransaction=self.ipn) | Q(ipn__subsequenttransactions=self.ipn)).distinct()

    # The following properties assume that all invoice items take the format
    # 'TYPE_TYPEID_ITEMID', which is enforced in the Core app and should be
    # enforced elsewhere so that we can parse the invoiceNumbers.
    @property
    def invoiceItemTypeName(self):
        return self.invoiceNumber.split('_')[0]

    @property
    def invoiceItemTypeId(self):
        try:
            return int(self.invoiceNumber.split('_')[1])
        except ValueError:
            return self.invoiceNumber.split('_')[1]

    @property
    def invoiceItemId(self):
        try:
            return int(self.invoiceNumber.split('_')[2])
        except ValueError:
            return self.invoiceNumber.split('_')[2]

    # The following property allocates the discounted total of an IPN Payment
    # across the items in the cart.  This is how revenue received is set
    # after successful IPN payments are used to create EventRegistrations.
    @property
    def allocatedNetPrice(self):
        return \
            self.mc_gross * (self.ipn.mc_gross / sum([
                x.mc_gross for x in self.ipn.ipncartitem_set.all()
            ]))

    @property
    def allocatedFees(self):
        return \
            self.ipn.mc_fee * (self.mc_gross / sum([
                x.mc_gross for x in self.ipn.ipncartitem_set.all()
            ]))

    @property
    def allocatedNetTotal(self):
        return sum([x.allocatedNetPrice for x in self.relatedCartItems.filter(ipn__payment_status='Completed')])

    @property
    def allocatedAdjustment(self):
        return sum([x.allocatedNetPrice for x in self.relatedCartItems.filter(ipn__payment_status='Refunded')])

    @property
    def allocatedTotalFees(self):
        return sum([x.allocatedFees for x in self.relatedCartItems.all()])

    @property
    def totalRefunds(self):
        return sum([x.refundAmount for x in self.relatedCartItems.filter(ipn__payment_status='Refunded')])

    def clean(self):
        # Non-initial transactions cannot also have subsequent transactions.
        if self.refundAmount != 0 and self.ipn.payment_status != 'Refunded':
            raise ValidationError(_('Refunds cannot be allocated for non-refund transaction types.'))

    def save(self,*args,**kwargs):
        '''
        Override the save method to create a related revenue item
        for this cart item if it does not already exist.
        '''
        super(IPNCartItem,self).save(*args,**kwargs)

        if self.initialCartItem == self and not self.revenueItem:
            logger.debug(_('Creating revenue item for IPN cart item %s.' % self.invoiceNumber))

            if self.invoiceItemTypeName in ['series','event']:
                this_category = RevenueCategory.objects.get(id=getConstant('financial__registrationsRevenueCatID'))

                event = Event.objects.get(id=self.invoiceItemTypeId)
                if event.series:
                    revenue_description = 'Series Registration ' + str(self.invoiceNumber) + ': ' + self.ipn.registration.firstName + ' ' + self.ipn.registration.lastName
                else:
                    revenue_description = 'Event Registration ' + str(self.invoiceNumber) + ': ' + self.ipn.registration.firstName + ' ' + self.ipn.registration.lastName
            else:
                event = None
                this_category = RevenueCategory.objects.get(id=getConstant('financial__unallocatedPaymentsRevenueCatID'))
                revenue_description = _('Paypal IPN Payment ' + str(self.invoiceNumber))

            new_item = RevenueItem.objects.create(
                paymentMethod=PAYPAL_PAYMENTMETHOD_ID,
                category=this_category,
                description=revenue_description,
                total=self.allocatedNetTotal,
                grossTotal=self.mc_gross,
                fees=self.allocatedTotalFees,
                event=event,
                received=True,
                receivedDate=self.ipn.payment_date,
                submissionUser=None,
                invoiceNumber=str(self.ipn.txn_id) + '_' + str(self.invoiceNumber),
            )
            self.revenueItem = new_item
            self.save()

        else:
            logger.debug(_('Updating totals for related RevenueItem object to IPNCartItem %s.' % self.invoiceNumber))
            for item in self.ipn.initialTransaction.ipncartitem_set.all():
                if item.revenueItem:
                    item.revenueItem.total = item.allocatedNetTotal
                    item.revenueItem.fees = item.allocatedTotalFees
                    # No longer adjusting revenueItems from initialCartItem allocations.
                    # item.revenueItem.adjustments = -1 * item.totalRefunds
                    item.revenueItem.save()

    class Meta:
        verbose_name = _('Paypal IPN Cart Item')


class PayNowFormModel(CMSPlugin):
    ''' This model holds options for instances of the GiftCertificateFormPlugin and the CartPaymentFormPlugin '''

    successPage = PageField(verbose_name=_('Success Page'),help_text=_('When the user returns to the site after a successful transaction, send them to this page.'),related_name='successPageFor')
    cancellationPage = PageField(verbose_name=_('Cancellation Page'),help_text=_('When the user returns to the site, send them to this page.'),related_name='cancellationPageFor')

    defaultAmount = models.FloatField(verbose_name=_('Default amount'),help_text=_('The initial value for gift certificate forms.'),default=0)
