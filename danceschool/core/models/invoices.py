from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db.models import Q, Sum, F, Case, When, Value, Count
from django.db.models.functions import Coalesce, Cast
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import uuid
import string
import random
import logging

from ..constants import getConstant
from ..helpers import getSiteUrl
from ..signals import invoice_finalized, invoice_cancelled
from ..mixins import EmailRecipientMixin
from ..managers import InvoiceManager, InvoiceItemManager

logger = logging.getLogger(__name__)


def get_validationString():
    return ''.join(random.choice(string.ascii_uppercase) for i in range(25))


class Invoice(EmailRecipientMixin, models.Model):

    class PaymentStatus(models.TextChoices):
        preliminary = ('0', _('Preliminary'))
        unpaid = ('U', _('Unpaid'))
        authorized = ('A', _('Authorized using payment processor'))
        paid = ('P', _('Paid'))
        needsCollection = ('N', _('Processed but no payment collected'))
        fullRefund = ('R', _('Refunded in full'))
        cancelled = ('C', _('Cancelled'))
        rejected = ('X', _('Rejected in processing'))
        error = ('E', _('Error in processing'))

    # The UUID field is the unique internal identifier used for this Invoice.
    # The validationString field is used only so that non-logged in users can view
    # an invoice.
    id = models.UUIDField(
        _('Invoice number'), primary_key=True, default=uuid.uuid4, editable=False
    )
    validationString = models.CharField(
        _('Validation string'), max_length=25, default=get_validationString, editable=False
    )

    # Invoices do not require that a recipient is specified, but doing so ensures
    # that invoice notifications can be sent.
    firstName = models.CharField(_('Recipient first name'), max_length=100, null=True, blank=True)
    lastName = models.CharField(_('Recipient last name'), max_length=100, null=True, blank=True)
    email = models.CharField(_('Recipient email address'), max_length=200, null=True, blank=True)

    creationDate = models.DateTimeField(_('Invoice created'), auto_now_add=True)
    modifiedDate = models.DateTimeField(_('Last modified'), auto_now=True)

    expirationDate = models.DateTimeField(
        _('Expiration date'),
        help_text=_(
            'Invoices that are not yet permanent (preliminary invoices) can ' +
            'expire and may automatically be removed if they are past their ' +
            'expireation date. Typically, these are invoices associated with ' +
            'temporary registrations that are never completed.'
        ),
        null=True, blank=True
    )

    status = models.CharField(
        _('Payment status'), max_length=1,
        choices=PaymentStatus.choices, default=PaymentStatus.preliminary
    )

    paidOnline = models.BooleanField(_('Paid Online'), default=False)
    submissionUser = models.ForeignKey(
        User, null=True, blank=True, verbose_name=_('Registered by user'),
        related_name='submittedinvoices', on_delete=models.SET_NULL
    )
    collectedByUser = models.ForeignKey(
        User, null=True, blank=True, verbose_name=_('Collected by user'),
        related_name='collectedinvoices', on_delete=models.SET_NULL
    )

    grossTotal = models.FloatField(
        _('Total before discounts'), validators=[MinValueValidator(0)], default=0
    )
    total = models.FloatField(
        _('Total billed amount'), validators=[MinValueValidator(0)], default=0
    )
    adjustments = models.FloatField(_('Refunds/adjustments'), default=0)
    taxes = models.FloatField(_('Taxes'), validators=[MinValueValidator(0)], default=0)
    fees = models.FloatField(_('Processing fees'), validators=[MinValueValidator(0)], default=0)
    buyerPaysSalesTax = models.BooleanField(_('Buyer pays sales tax'), default=False)

    amountPaid = models.FloatField(
        default=0, verbose_name=_('Net Amount Paid'), validators=[MinValueValidator(0)]
    )

    comments = models.TextField(_('Comments'), null=True, blank=True)

    # Additional information (record of specific transactions) can go in here
    data = models.JSONField(_('Additional data'), blank=True, default=dict)

    # This custom manager prevents deletion of Invoices that are not preliminary,
    # even using queryset methods. It also adds a net annotation so net revenue
    # is calculated consistently.
    objects = InvoiceManager()

    @property
    def fullName(self):
        return ' '.join([self.firstName or '', self.lastName or '']).strip()
    fullName.fget.short_description = _('Name')

    @property
    def itemsEditable(self):
        ''' Only allow invoices to be edited if their status permits it. '''
        return (self.status in [
            self.PaymentStatus.preliminary,
            self.PaymentStatus.unpaid,
        ])

    @property
    def preliminary(self):
        return (self.status == self.PaymentStatus.preliminary)
    preliminary.fget.short_description = _('Preliminary')

    @property
    def unpaid(self):
        return (self.status != self.PaymentStatus.paid)
    unpaid.fget.short_description = _('Unpaid')

    @property
    def modified(self):
        '''
        Used to add additional context in views if an invoice has been updated
        since its creation. '''
        return (self.modifiedDate - self.creationDate) >= timedelta(seconds=1)

    @property
    def outstandingBalance(self):
        balance = self.total + self.adjustments - self.amountPaid
        if self.buyerPaysSalesTax:
            balance += self.taxes
        return round(balance, 2)
    outstandingBalance.fget.short_description = _('Outstanding balance')

    @property
    def refunds(self):
        return -1 * self.adjustments
    refunds.fget.short_description = _('Amount refunded')

    @property
    def unallocatedAdjustments(self):
        return self.adjustments - sum([x.adjustments for x in self.invoiceitem_set.all()])
    unallocatedAdjustments.fget.short_description = _('Unallocated adjustments')

    @property
    def refundsAllocated(self):
        return (self.unallocatedAdjustments == 0)
    refundsAllocated.fget.short_description = _('All refunds are allocated')

    @property
    def initialTotal(self):
        return sum([x.initialTotal for x in self.invoiceitem_set.all()])

    @property
    def netRevenue(self):
        net = getattr(self, 'net', None)
        if net is None:
            net = self.total - self.fees + self.adjustments
            if not self.buyerPaysSalesTax:
                net -= self.taxes
        return net
    netRevenue.fget.short_description = _('Net revenue')

    @property
    def discounted(self):
        return (self.total != self.grossTotal)
    discounted.fget.short_description = _('Is discounted')

    @property
    def discountPercentage(self):
        return 1 - (self.total / self.grossTotal)
    discountPercentage.fget.short_description = _('Discount percentage')

    @property
    def itemTotalMismatch(self):
        item_totals = self.invoiceitem_set.aggregate(
            grossTotal=Coalesce(Sum('grossTotal'), 0, output_field=models.FloatField()),
            total=Coalesce(Sum('total'), 0, output_field=models.FloatField()),
        )
        return (
            self.grossTotal != item_totals.get('grossTotal') or
            self.total != item_totals.get('total')
        )

    @property
    def statusLabel(self):
        '''
        This is needed so we have a property not a callable for
        EventRegistrationJsonView
        '''
        return self.get_status_display()
    statusLabel.fget.short_description = _('Status')

    @property
    def parent_items(self):
        return self.invoiceitem_set.filter(parent_item__isnull=True)

    @property
    def url(self):
        '''
        Because invoice URLs are generally emailed, this
        includes the default site URL and the protocol specified in
        settings.
        '''
        if self.id:
            return '%s%s' % (
                getSiteUrl(),
                reverse('viewInvoice', args=[self.id, ]),
            )
    url.fget.short_description = _('Invoice URL')

    def get_absolute_url(self):
        '''
        For adding 'View on Site' links to the admin
        '''
        return '{}?v={}'.format(
            reverse('viewInvoice', args=[self.id, ]),
            self.validationString
        )

    def get_default_recipients(self):
        '''
        Overrides EmailRecipientMixin by getting the set of associated email
        addresses and removing blanks.
        '''
        email_set = set([
            self.email,
        ])
        email_set.difference_update([None, ''])
        return list(email_set)

    def get_email_context(self, **kwargs):
        ''' Overrides EmailRecipientMixin '''
        context = super().get_email_context(**kwargs)
        context.update({
            'firstName': self.firstName,
            'lastName': self.lastName,
            'email': self.email,
            'id': self.id,
            'url': '%s?v=%s' % (self.url, self.validationString),
            'amountPaid': self.amountPaid,
            'outstandingBalance': self.outstandingBalance,
            'status': self.get_status_display(),
            'creationDate': self.creationDate,
            'modifiedDate': self.modifiedDate,
            'paidOnline': self.paidOnline,
            'grossTotal': self.grossTotal,
            'total': self.total,
            'adjustments': self.adjustments,
            'taxes': self.taxes,
            'fees': self.fees,
            'comments': self.comments,
            'itemList': [
                x.get_email_context() for x in
                self.invoiceitem_set.all()
            ],
        })
        if getattr(self, 'registration', None):
            context.update(self.registration.get_email_context())

        return context

    def get_payments(self):
        '''
        Since there may be many payment processors, this method simplifies the
        process of getting the list of payments
        '''
        return self.paymentrecord_set.order_by('creationDate')

    def get_payment_method(self):
        '''
        Since there may be many payment processors, this just gets the reported payment
        method name for the first payment method used.
        '''
        payments = self.get_payments()
        if payments:
            return payments.first().methodName

    def processPayment(
        self, amount, fees, paidOnline=True, methodName=None, methodTxn=None,
        submissionUser=None, collectedByUser=None, forceFinalize=False,
        notify=None, epsilon=0.01
    ):
        '''
        When a payment processor makes a successful payment against an invoice, it can call this method
        which handles status updates, the creation of a final registration object (if applicable), and
        the firing of appropriate registration-related signals.
        '''

        paymentTime = timezone.now()

        logger.info('Processing payment and creating registration objects if applicable.')

        # The payment history record is primarily for convenience, and passed values are not
        # validated.  Payment processing apps should keep individual transaction records with
        # a ForeignKey to the Invoice object.
        paymentHistory = self.data.get('paymentHistory', [])
        paymentHistory.append({
            'dateTime': paymentTime.isoformat(),
            'amount': amount,
            'fees': fees,
            'paidOnline': paidOnline,
            'methodName': methodName,
            'methodTxn': methodTxn,
            'submissionUser': getattr(submissionUser, 'id', None),
            'collectedByUser': getattr(collectedByUser, 'id', None),
        })
        self.data['paymentHistory'] = paymentHistory

        self.paidOnline = paidOnline
        self.amountPaid += amount

        if submissionUser and not self.submissionUser:
            self.submissionUser = submissionUser
        if collectedByUser and not self.collectedByUser:
            self.collectedByUser = collectedByUser

        # if this completed the payment, then mark
        # the invoice as Paid unless told to do otherwise.
        if forceFinalize or abs(self.outstandingBalance) < epsilon:
            self.status = self.PaymentStatus.paid

            if getattr(self, 'registration', None):
                self.registration = self.registration.finalize(dateTime=paymentTime)

            self.sendNotification(invoicePaid=True, thisPaymentAmount=amount, payerEmail=notify)
        else:
            # The payment wasn't completed so don't finalize, but do send a notification recording the payment.
            if notify:
                self.sendNotification(invoicePaid=True, thisPaymentAmount=amount, payerEmail=notify)
            else:
                self.sendNotification(invoicePaid=True, thisPaymentAmount=amount)

        if fees:
            self.updateTotals(forceSave=True, allocateAmounts={'fees': fees,})
        else:
            self.save()

    def updateTotals(
        self, save=True, forceSave=False, allocateAmounts={},
        allocateWeights={}, prior_queryset=None, setAdjustmentsFlag=True
    ):
        '''
        This method recalculates the totals from the invoice items associated
        with the invoice.  If the totals have changed, then the invoice is
        saved.  If an allocate dictionary is passed, then adjustments to each
        line item can also be proportionately distributed among the items.  And,
        a dictionary of weights (in {id: value} form) can be passed, which
        allows allocations to be applied to specific items in proportion.

        Because of the recalculation of taxes, we have to calculate all of the
        various line items whenever we are allocating amounts.  Unless weights
        are specified, changes to the grossTotal or the total price are
        allocated based on the ratio of grossTotal across invoice items. New
        taxes are always calculated based on the new total price after any
        changes (to ensure consistent application of tax rates).  Changes to the
        adjustments line are then allocated based on the ratio of the
        newTotal + newTax for each item, and changes to fees are then allocated
        based on the updated ratio of total + tax + adjustments for each item.

        When specific weights are specified, allocations must be either all
        pre-tax or all post-tax.  This prevents issues associated with things
        such as applying full-price after tax vouchers at the same time as
        discounts that might affect the calculation of tax.  This method returns
        a queryset of invoice items with annotations that indicate the outcome
        of any allocations, and it takes as an argument the queryset that
        resulted from a prior call to this method.  This way, even if the
        results of an allocation are not saved, pre-tax and post-tax updates
        can be processed by calling this method twice.  Passed weights are
        automatically rescaled to 1.

        Finally, note that this method does not check individual item totals for
        bounds or sign.  If you pass allocation weights that are not sensible
        for the underlying items, then allocations may happen in a way that
        leads to negative net prices or negative processing fees.  Use caution
        when making use of this method.
        '''

        '''
        existing_ids = [str(x) for x in self.invoiceitem_set.values_list('id', flat=True)]
        not_existing = [k for k in allocateWeights.keys() if k not in existing_ids]
        if not_existing:
            raise ValueError(_('Invalid allocation weight identifier passed. to updateTotals()'))
        '''

        item_keys = ['grossTotal', 'total', 'adjustments', 'fees']

        # Ignore keys other than the ones that apply to invoice items and
        # also 0 adjustment amounts
        allocateAmounts = {
            k: x for k, x in allocateAmounts.items() if abs(x) != 0 and
            k in item_keys
        }

        # Capture each item's pre-application `total` and `adjustments` into
        # its own data dict so the back-button reset block below can restore
        # them faithfully. Without this, an item created with a non-zero
        # adjustment (e.g. a manual courtesy credit applied before a discount
        # is computed) would be wiped to 0 on the retry pass because the
        # reset's Coalesce(...) defaults to 0 when the key is absent. Items
        # that already have `_initial_*` captured are not re-captured.
        for item in self.invoiceitem_set.all():
            item_data = item.data or {}
            captured = False
            if '_initial_adjustments' not in item_data:
                item_data['_initial_adjustments'] = item.adjustments
                captured = True
            if '_initial_total' not in item_data:
                item_data['_initial_total'] = item.total
                captured = True
            if captured:
                item.data = item_data
                item.save(updateInvoiceTotals=False)

        # If the invoice has previously been saved with adjustments
        # but it is still a preliminary invoice,
        # then we need to un-apply those previous adjustments by starting with
        # the total equal to grossTotal and with adjustments equal to 0.  This
        # prevents the duplicate application of discounts and vouchers by
        # pressing the back button.  The saved_adjustments flag in Invoice
        # data is set later in updateTotals() whenever the invoice is saved.
        saved_adjustments = self.data.pop('saved_adjustments', False)
        if (saved_adjustments and self.status == self.PaymentStatus.preliminary):
            prior_queryset = self.invoiceitem_set.all()
            prior_queryset.update(
                total=Coalesce(
                    Cast('data___initial_total', models.FloatField()),
                    'grossTotal'
                ),
                adjustments=Coalesce(
                    Cast('data___initial_adjustments', models.FloatField()),
                    0, output_field=models.FloatField()
                )
            )
            aggregates = prior_queryset.aggregate(Sum('total'), Sum('adjustments'))
            self.adjustments = aggregates.get('adjustments__sum', 0) or 0
            self.total = aggregates.get('total__sum', 0) or 0
            self.save(sendSignals=False)

        # before going any further, we need to ensure that the queryset to be
        # handled begins with the same format, which means that all the "old"
        # values must be put into annotations to avoid name conflicts.
        items = prior_queryset or self.invoiceitem_set.all()

        if 'newGrossTotal' in items.query.annotations:
            items = items.annotate(
                oldGrossTotal=F('newGrossTotal'),
                oldTotal=F('newTotal'),
                oldTaxes=F('newTaxes'),
                oldAdjustments=F('newAdjustments'),
                oldFees=F('newFees'),
            )
        else:
            items = items.annotate(
                oldGrossTotal=F('grossTotal'),
                oldTotal=F('total'),
                oldTaxes=F('taxes'),
                oldAdjustments=F('adjustments'),
                oldFees=F('fees'),
            )

        # Now, construct the allocation weights, which can be applied either
        # pre-tax or post-tax, but not both.
        if allocateWeights:
            pretax_allocations = [x for x in allocateAmounts.keys() if x in ['grossTotal', 'total']]
            posttax_allocations = [x for x in allocateAmounts.keys() if x in ['adjustments', 'fees']]

            if pretax_allocations and posttax_allocations:
                raise ValueError(_(
                    'Cannot use Invoice.updateTotals() to allocate both ' +
                    'pre-tax and post-tax amounts with allocation weights. ' +
                    'Use the returned queryset of a pre-tax allocation to ' +
                    'submit a separate post-tax allocation instead.'
                ))

            # Get rescaled weights, with one item for each passed ID.  Also
            # create a binary indicator that the weight is greater than 0.
            totalWeight = sum([x for x in allocateWeights.values()])
            allocateWeights = {
                k: (v / totalWeight) if totalWeight > 0 else 0
                for k,v in allocateWeights.items()
            }

            when_weight = []
            for k,v in allocateWeights.items():
                when_weight.append(When(id=k, then=v))

            items = items.annotate(
                allocationWeight=Case(*when_weight, default=0, output_field=models.FloatField())
            )

        total_aggregation = {
            k: Coalesce(
                Sum(k2, output_field=models.FloatField()), 0, output_field=models.FloatField()
            ) for k,k2 in [
                ('grossTotal', 'oldGrossTotal'), ('total', 'oldTotal'),
                ('taxes', 'oldTaxes'), ('adjustments', 'oldAdjustments'),
                ('fees', 'oldFees'),
            ]
        }

        old_totals = items.aggregate(item_count=Count('id'),**total_aggregation)
        new_totals = old_totals.copy()

        for k,v in allocateAmounts.items():
            new_totals[k] += v

        pretax_annotations = {
            'buyerTax': Value(float(self.buyerPaysSalesTax), output_field=models.FloatField()),
        }

        # Used to avoid division by zero issues when constructing allocation ratios.
        proportional = Value(1/(old_totals['item_count'] or 1), output_field=models.FloatField())

        # If no weights are specified, the ratio to be applied to grossTotal is
        # based on prior values of grossTotal.  For all other fields, the ratio
        # be applied is based on the update values of previous fields in the
        # order of operations.
        if allocateWeights and allocateAmounts.get('grossTotal'):
            pretax_annotations['grossTotalRatio'] = F('allocationWeight')
        elif old_totals['grossTotal'] == 0:
            pretax_annotations['grossTotalRatio'] = proportional
        else:
            pretax_annotations['grossTotalRatio'] = (F('oldGrossTotal')/old_totals['grossTotal'])

        pretax_annotations['newGrossTotal'] = (
            F('oldGrossTotal') + (F('grossTotalRatio') * allocateAmounts.get('grossTotal', 0))
        )

        if allocateWeights and allocateAmounts.get('total'):
            pretax_annotations['totalRatio'] = F('allocationWeight')
        elif new_totals['grossTotal'] == 0:
            pretax_annotations['totalRatio'] = proportional
        else:
            pretax_annotations['totalRatio'] = (F('newGrossTotal')/new_totals['grossTotal'])

        pretax_annotations.update({
            'newTotal': F('oldTotal') + (F('totalRatio') * allocateAmounts.get('total',0)),
            'newTaxes': F('newTotal') * (F('taxRate') / 100),
        })

        items = items.annotate(**pretax_annotations)
        new_totals['taxes'] = items.aggregate(
            newTaxes__sum=Coalesce(
                Sum('newTaxes', output_field=models.FloatField()),
                0, output_field=models.FloatField()
            )
        ).get('newTaxes__sum')

        posttax_annotations = {}

        if allocateWeights and allocateAmounts.get('adjustments'):
            posttax_annotations['adjustmentRatio'] = F('allocationWeight')
        elif new_totals['total'] + new_totals['taxes'] == 0:
            posttax_annotations['adjustmentRatio'] = proportional
        else:
            posttax_annotations['adjustmentRatio'] = (
                (F('newTotal') + F('newTaxes')) / (new_totals['total'] + new_totals['taxes'])
            )

        posttax_annotations['newAdjustments'] = F('oldAdjustments') + (
            F('adjustmentRatio') * allocateAmounts.get('adjustments', 0)
        )

        if allocateWeights and allocateAmounts.get('fees'):
            posttax_annotations['feesRatio'] = F('allocationWeight')
        elif new_totals['total'] + new_totals['taxes'] + new_totals['adjustments'] == 0:
            posttax_annotations['feesRatio'] = proportional
        else:
            posttax_annotations['feesRatio'] = (
                (F('newTotal') + F('newTaxes') + F('newAdjustments')) /
                (new_totals['total'] + new_totals['taxes'] + new_totals['adjustments'])
            )

        posttax_annotations['newFees'] = F('oldFees') + (F('feesRatio') * allocateAmounts.get('fees', 0))

        items = items.annotate(**posttax_annotations)

        if save or forceSave:
            updates = {
                'grossTotal': F('newGrossTotal'),
                'total': F('newTotal'),
                'taxes': F('newTaxes'),
                'adjustments': F('newAdjustments'),
                'fees': F('newFees'),
            }
            items.update(**updates)

        changed_invoice = False

        # This should happen if we have allocated changes (regardless of whether
        # we save the items), or if the Invoice items have been changed since
        # the last time this was run.  Since this method is called on every
        # InvoiceItem save or delete call, this keeps the Invoice in sync with
        # the items.  However, we use the new_totals dictionary rather than
        # a query because the items are not always saved when adjustments are
        # made.
        for k in item_keys + ['taxes']:
            if getattr(self,k) != new_totals[k]:
                setattr(self, k, new_totals[k])
                changed_invoice = True

        if (changed_invoice and save) or forceSave:
            if changed_invoice and setAdjustmentsFlag:
                self.data['saved_adjustments'] = True
            self.save()

            # Clear the annotations from the queryset if we have saved to avoid confusion.
            # The line items now reflect the updated values.
            items.query.annotations.clear()

        return items

    def sendNotification(self, **kwargs):

        if getConstant('email__disableSiteEmails'):
            logger.info('Sending of invoice email is disabled.')
            return
        logger.info('Sending invoice notification to customer.')

        payerEmail = kwargs.pop('payerEmail', '')
        amountDue = kwargs.pop('amountDue', self.outstandingBalance)

        if not payerEmail and not self.get_default_recipients():
            logger.info('Cannot send notification email because no recipient has been specified.')
            return

        registration = getattr(self, 'registration', None)

        if registration and getattr(registration, 'final', False):
            template = getConstant('email__registrationSuccessTemplate')
        else:
            template = getConstant('email__invoiceTemplate')

        self.email_recipient(
            subject=template.subject,
            content=template.content,
            html_content=template.html_content,
            send_html=template.send_html,
            from_address=template.defaultFromAddress,
            from_name=template.defaultFromName,
            cc=template.defaultCC,
            bcc=[payerEmail, ],
            amountDue=amountDue,
            **kwargs
        )
        logger.debug('Invoice notification sent.')

    def __init__(self, *args, **kwargs):
        ''' Keep track of initial status in memory to detect status changes. '''
        super().__init__(*args, **kwargs)
        self.__initial_status = self.status

    def save(self, *args, **kwargs):
        '''
        If the invoice has been cancelled or finalized, then fire the signals
        that will keep associated registrations or merch orders in sync with
        this status.
        '''

        restrictStatus = kwargs.pop('restrictStatus', True)
        sendSignals = kwargs.pop('sendSignals', True)

        # Do not permit the status of paid invoices to be changed except to
        # process refunds or indicate that collection is needed.
        if (
            restrictStatus and
            self.__initial_status == self.PaymentStatus.paid and
            self.status not in [
                self.PaymentStatus.paid, self.PaymentStatus.fullRefund,
                self.PaymentStatus.needsCollection
            ]
        ):
            self.status = self.__initial_status

        super().save(*args, **kwargs)

        if (
            sendSignals and
            self.status in [self.PaymentStatus.cancelled, self.PaymentStatus.fullRefund] and
            self.status != self.__initial_status
        ):
            invoice_cancelled.send(
                sender=Invoice,
                invoice=self,
            )
        if (
            sendSignals and
            self.status in [self.PaymentStatus.paid, self.PaymentStatus.needsCollection] and
            self.status != self.__initial_status
        ):
            invoice_finalized.send(
                sender=Invoice,
                invoice=self,
            )
        self.__initial_status = self.status

    def delete(self, *args, **kwargs):
        '''
        Only allow deletions of invoices that are preliminary.  Paid invoices
        are ignored.  All other invoices are cancelled.
        '''
        if self.status == self.PaymentStatus.preliminary:
            super().delete(*args, **kwargs)
        elif self.status != self.PaymentStatus.paid:
            self.status = self.PaymentStatus.cancelled
            self.save()


    @classmethod
    def create_from_item(cls, amount, item_description, **kwargs):
        '''
        Creates an Invoice as well as a single associated InvoiceItem
        with the passed description (for things like gift certificates)
        '''
        submissionUser = kwargs.pop('submissionUser', None)
        collectedByUser = kwargs.pop('collectedByUser', None)
        calculate_taxes = kwargs.pop('calculate_taxes', False)
        grossTotal = kwargs.pop('grossTotal', None)
        status = kwargs.pop('status', cls.PaymentStatus.preliminary)
        tax_rate = kwargs.pop('tax_rate', None) or 0

        new_invoice = cls(
            grossTotal=grossTotal or amount,
            total=amount,
            submissionUser=submissionUser,
            collectedByUser=collectedByUser,
            buyerPaysSalesTax=getConstant('registration__buyerPaysSalesTax'),
            status=status,
            data=kwargs,
        )
        new_invoice.save()

        item = InvoiceItem(
            invoice=new_invoice,
            grossTotal=grossTotal or amount,
            total=amount,
            description=item_description,
            taxRate=tax_rate,
        )
        if calculate_taxes:
            item.calculateTaxes()
        item.save()

        return new_invoice

    class Meta:
        ordering = ('-modifiedDate',)
        verbose_name = _('Invoice')
        verbose_name_plural = _('Invoices')
        permissions = (
            ('view_all_invoices', _('Can view invoices without passing the validation string.')),
            ('send_invoices', _('Can send invoices to students requesting payment')),
            ('process_refunds', _('Can refund customers for registrations and other invoice payments.')),
            ('export_invoice_data', _('Can export data related to invoices and their items')),
        )


class InvoiceItem(models.Model):
    '''
    Since we potentially want to facilitate financial tracking by Event and not
    just by period, we have to create a unique record for each item in each invoice.
    In the financial app (if installed), RevenueItems may link uniquely to InvoiceItems,
    and InvoiceItems may link uniquely to registration items.  Although this may seem
    like duplicated functionality, it permits the core app (as well as the payment apps)
    to operate completely independently of the financial app, making that app fully optional.

    Note also that handlers.py has post_save and post_delete signal handlers that
    ensure that the invoice totals are kept current with the set of associated
    invoice items.
    '''

    # The UUID field is the unique internal identifier used for this InvoiceItem
    id = models.UUIDField(
        _('Invoice item number'), primary_key=True, default=uuid.uuid4, editable=False
    )
    invoice = models.ForeignKey(Invoice, verbose_name=_('Invoice'), on_delete=models.CASCADE)

    parent_item = models.ForeignKey(
        'self', on_delete=models.CASCADE, related_name='child_items',
        null=True, blank=True
    )

    description = models.CharField(_('Description'), max_length=300, null=True, blank=True)

    grossTotal = models.FloatField(
        _('Total before discounts'), validators=[MinValueValidator(0)], default=0
    )
    total = models.FloatField(
        _('Total billed amount'), validators=[MinValueValidator(0)], default=0
    )
    adjustments = models.FloatField(_('Refunds/adjustments'), default=0)

    taxRate = models.FloatField(
        _('Sales tax rate'), validators=[MinValueValidator(0)], default=0,
        help_text=_(
            'This rate is used to update the tax line item when discounts ' +
            'or other pre-tax price adjustments are applied.  Enter as a ' +
            'whole number (e.g. 6 for 6%).'
        ),
    )
    taxes = models.FloatField(_('Taxes'), validators=[MinValueValidator(0)], default=0)

    fees = models.FloatField(_('Processing fees'), validators=[MinValueValidator(0)], default=0)

    data = models.JSONField(_('Additional data'), blank=True, default=dict)

    # This custom manager adds a net annotation so net revenue is calculated
    # consistently.
    objects = InvoiceItemManager()

    @property
    def grossTotalWithAllocation(self):
        '''
        Items that are parent items to other items will have a gross total line
        that does not reflect the value of the collection of items. This
        property adds the sum over the child items as well.
        '''
        return (
            self.grossTotal +
            (self.child_items.aggregate(Sum('grossTotal')).get('grossTotal__sum',0) or 0)
        )

    @property
    def initialTotal(self):
        return self.data.get('_initial_total', self.grossTotal)

    @property
    def initialTotalWithAllocation(self):
        return (
            self.grossTotal +
            (self.child_items.annotate(
                initial_total=Coalesce(
                    Cast('data___initial_total', models.FloatField()),
                    'grossTotal'
                )
            ).aggregate(Sum('initial_total')).get('initial_total__sum',0) or 0)
        )

    @property
    def totalWithAllocation(self):
        return (
            self.total +
            (self.child_items.aggregate(Sum('total')).get('total__sum',0) or 0)
        )

    @property
    def taxesWithAllocation(self):
        return (
            self.taxes +
            (self.child_items.aggregate(Sum('taxes')).get('taxes__sum',0) or 0)
        )

    @property
    def feesWithAllocation(self):
        return (
            self.fees +
            (self.child_items.aggregate(Sum('fees')).get('fees__sum',0) or 0)
        )

    @property
    def adjustmentsWithAllocation(self):
        return (
            self.adjustments +
            (self.child_items.aggregate(Sum('adjustments')).get('adjustments__sum',0) or 0)
        )

    @property
    def netAllocationAdjustment(self):
        '''
        This is the difference in allocated gross and net totals before discounts
        are applied. So, for example, this represents the savings from purchasing
        an all-in pass rather than the individual items it contains.
        '''
        return self.initialTotalWithAllocation - self.grossTotalWithAllocation

    @property
    def netRevenue(self):
        net = getattr(self, 'net', None)
        if net is None:
            net = self.total - self.fees + self.adjustments
            if not self.invoice.buyerPaysSalesTax:
                net -= self.taxes
        return net
    netRevenue.fget.short_description = _('Net revenue')

    @property
    def name(self):
        er = getattr(self, 'eventRegistration', None)
        if er and er.dropIn:
            return _('Drop-in Registration: %s' % er.event.name)
        elif er:
            return _('Registration: %s' % er.event.name)
        else:
            return self.description or _('Other items')
    name.fget.short_description = _('Name')

    def calculateTaxes(self):
        '''
        Updates the tax field to reflect the amount of taxes depending on
        the local rate as well as whether the buyer or seller pays sales tax on
        this invoice.
        '''
        from .event_types import Series

        if not self.taxRate:
            er = getattr(self, 'eventRegistration', None)
            if er and isinstance(er.event, Series):
                self.taxRate = getConstant('registration__seriesSalesTaxRate') or 0
            elif er:
                self.taxRate = getConstant('registration__publicEventSalesTaxRate') or 0

        if self.taxRate > 0:
            if self.invoice.buyerPaysSalesTax:
                # If the buyer pays taxes, then taxes are just added as a fraction of the price
                self.taxes = self.total * (self.taxRate / 100)
            else:
                # If the seller pays sales taxes, then adjusted_total will be their net revenue,
                # and under this calculation adjusted_total + taxes = the price charged
                adjusted_total = self.total / (1 + (self.taxRate / 100))
                self.taxes = adjusted_total * (self.taxRate / 100)

    def get_email_context(self, **kwargs):
        ''' Provides additional context for invoice items. '''
        kwargs.update({
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'grossTotal': self.grossTotal,
            'total': self.total,
            'adjustments': self.adjustments,
            'taxes': self.taxes,
            'fees': self.fees,
        })

        er = getattr(self, 'eventRegistration', None)
        if er:
            kwargs['eventRegistration'] = er.get_email_context(
                includeName=False, includeEvent=True
            )
        return kwargs

    def save(self, *args, **kwargs):
        restrictStatus = kwargs.pop('restrictStatus', True)
        updateTotals = kwargs.pop('updateInvoiceTotals', True)
        if self.invoice.itemsEditable or not restrictStatus:
            super().save(*args, **kwargs)
            if updateTotals:
                self.invoice.updateTotals()


    def delete(self, *args, **kwargs):
        restrictStatus = kwargs.pop('restrictStatus', True)
        updateTotals = kwargs.pop('updateInvoiceTotals', True)
        invoice = self.invoice
        if self.invoice.itemsEditable or not restrictStatus:
            super().delete(*args, **kwargs)
            if updateTotals:
                invoice.updateTotals()

    def __str__(self):
        return '%s: #%s' % (self.name, self.id)

    class Meta:
        verbose_name = _('Invoice item')
        verbose_name_plural = _('Invoice items')

        constraints = [
            models.CheckConstraint(
                check=~Q(parent_item=F('id')),
                name='no_self_parent_items',
            )
        ]
