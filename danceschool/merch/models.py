from django.db import models
from django.db.models import Q, F, Sum
from django.db.models.constraints import CheckConstraint
from django.core.validators import MinValueValidator, RegexValidator
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from filer.fields.image import FilerImageField
from djchoices import DjangoChoices, ChoiceItem
from cms.models.pluginmodel import CMSPlugin

from danceschool.core.models import Invoice, InvoiceItem
from danceschool.core.constants import getConstant
from danceschool.door.models import DoorRegisterPaymentMethod


def get_defaultSalesTaxRate():
    ''' Callable for default used by MerchItem class '''
    return getConstant('registration___merchSalesTaxRate')


def get_defaultBuyerPaysSalesTax():
    ''' Callable for default used by MerchItem class '''
    return getConstant('registration___merchBuyerPaysSalesTax')


class MerchItemCategory(models.Model):
    '''
    A category of merchandise product.  Used for determining the set of
    merchandise items to display as options for sale.
    '''

    name = models.CharField(
        _('Name'), max_length=100,
        help_text=_('Give a descriptive name for this category.')
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Merchandise category')
        verbose_name_plural = _('Merchandise category')
        ordering = ['name', ]
        

class MerchItem(models.Model):
    '''
    A basic product that can be sold.  A MerchItem may have one or more
    MerchItemVariants associated with it, representing things like
    different sizes or colors.
    '''

    name = models.CharField(
        _('Name'), max_length=100,
        help_text=_('Give a descriptive name for this item.')
    )

    category = models.ForeignKey(
        MerchItemCategory,
        help_text=_('Used on product pages to determine what items to list.'),
        on_delete=models.SET_NULL, null=True
    )

    description = models.TextField(
        _('Item Description'), null=True, blank=True,
        help_text=_('Provide a full item description for customers.')
    )

    defaultPrice = models.FloatField(
        _('Default price'), default=0, validators=[MinValueValidator(0)],
        help_text=_(
            'This price may be overridden by a particular item variant.'
        )
    )

    salesTaxRate = models.FloatField(
        _('Sales tax rate'),
        default=get_defaultSalesTaxRate, validators=[MinValueValidator(0)],
        help_text=_(
            'The sales tax percentage rate to be applied to this item (e.g. ' +
            'enter \'10\' to apply 10 percent sales tax).'
        )
    )

    buyerPaysSalesTax = models.BooleanField(
        _('Buyer pays sales tax (added to total price)'),
        default=get_defaultBuyerPaysSalesTax,
        help_text = _(
            'If unchecked, then the buyer will not be charged sales tax directly, ' +
            'but the amount of tax collected by the business will be reported.'
        )
    )

    photo = FilerImageField(
        verbose_name=_('Photo'), on_delete=models.SET_NULL, blank=True,
        null=True, related_name='item_photo',
        help_text=_('Individual item variants may have their own photos.')
    )

    disabled = models.BooleanField(
        _('Item disabled'), default=False,
        help_text=_(
            'If checked, then this item will not be available for purchase, '
            'regardless of current inventory.'
        )
    )

    creationDate = models.DateTimeField(_('Creation Date'), auto_now_add=True)

    @property
    def fullName(self):
        return self.name

    @property
    def soldOut(self):
        return self.item_variant.exclude(soldOut=True).exists()

    @property
    def numVariants(self):
        return self.item_variant.count()
    numVariants.fget.short_description = _('# Variants')

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Merchandise item')
        verbose_name_plural = _('Merchandise items')


class MerchItemVariant(models.Model):
    '''
    An individual variant of a MerchItem. For example, a particular
    size or color.
    '''
    item = models.ForeignKey(
        MerchItem, on_delete=models.CASCADE, related_name='item_variant',
        verbose_name=_('Item'),
    )

    sku = models.CharField(
        _('SKU'), unique=True, max_length=100,
        validators=[RegexValidator(regex=r'^[a-zA-Z\-_0-9]+$')],
        help_text=_(
            'The SKU for this item variant.'
        )
    )

    name = models.CharField(
        _('Name'), max_length=100, null=True, blank=True,
        help_text=_(
            'Give a unique name for this variant (e.g. "Size Medium")'
        )
    )

    price = models.FloatField(
        _('Price'),
        null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text=_(
            'If specified, then price supercedes the item default price.'
        )
    )

    photo = FilerImageField(
        verbose_name=_('Photo'), on_delete=models.SET_NULL, blank=True,
        null=True, related_name='itemvariant_photo',
        help_text=_('A photo specific to this variant, if applicable.')
    )

    originalQuantity = models.PositiveIntegerField(
        _('Original Quantity'),
        help_text=_(
            'For inventory purposes, enter an initial quantity here'
        ),
        validators=[MinValueValidator(0)]
    )

    # This is stored as a database field rather than dynamically generated as
    # a property, so that we can easily construct database queries that only
    # include items/variants that are not sold out.  On MerchItem, this is a
    # property.
    soldOut = models.BooleanField(_('Sold out'), default=False)

    @property
    def fullName(self):
        return '{}: {}'.format(self.item.name, self.name)

    @property
    def currentInventory(self):
        return (
            (self.originalQuantity or 0) +
            (self.quantity_adjustments.aggregate(total=Sum('amount')).get('total', 0) or 0) -
            (
                self.orders.exclude(
                    order__status__in=[
                        MerchOrder.OrderStatus.unsubmitted,
                        MerchOrder.OrderStatus.cancelled,
                    ]
                ).aggregate(total=Sum('quantity')).get('total', 0) or 0
            )
        )
    currentInventory.fget.short_description = _('Current inventory')

    def getPrice(self):
        if self.price is not None:
            return self.price
        return self.item.defaultPrice

    def updateSoldOut(self, commit=True):
        '''
        This should be called whenever an order is completed or inventory is
        adjusted.
        '''

        changed = False
        if self.currentInventory > 0 and self.soldOut:
            self.soldOut = False
            changed = True
        elif self.currentInventory <= 0 and not self.soldOut:
            self.soldOut = True
            changed = True

        if commit and changed:
            self.save()

    def __str__(self):
        return '{} ({})'.format(self.fullName, self.sku)

    class Meta:
        verbose_name = _('Item variant')
        verbose_name_plural = _('Item variants')
        unique_together = ('item', 'name',)


class MerchQuantityAdjustment(models.Model):

    variant = models.ForeignKey(
        MerchItemVariant, on_delete=models.CASCADE,
        related_name='quantity_adjustments'
    )

    amount = models.IntegerField(
        _('Change in inventory quantity'), default=0
    )

    submissionDate = models.DateTimeField(_('Submission Date'), auto_now_add=True)

    def save(self, *args, **kwargs):
        ''' Update the sold out status of the associated item variant. '''
        super().save(*args, **kwargs)
        self.variant.updateSoldOut()

    def __str__(self):
        return str(_('Inventory adjustment for {itemName}, {submissionDate}'.format(
            itemName=self.variant.fullName, submissionDate=self.submissionDate)
        ))


class MerchOrder(models.Model):

    class OrderStatus(DjangoChoices):
        unsubmitted = ChoiceItem('UN', _('Not yet submitted'))
        submitted = ChoiceItem('SU', _('Submitted'))
        approved = ChoiceItem('AP', _('Approved for fulfillment'))
        fulfilled = ChoiceItem('F', _('Fulfilled'))
        cancelled = ChoiceItem('C', _('Cancelled'))

    status = models.CharField(
        _('Order status'), max_length=2, choices=OrderStatus.choices,
        default=OrderStatus.unsubmitted,
        help_text=_(
            'Use the order status to keep track of submission, processing, ' +
            'shipment (if applicable), and fulfillment.'
        )
    )

    invoice = models.OneToOneField(
        Invoice, on_delete=models.CASCADE, null=True, blank=True,
        related_name='merchOrder',
        help_text=_(
            'All submitted merchandise orders must be associated with an invoice.'
        )
    )

    creationDate = models.DateTimeField(_('Creation Date'), auto_now_add=True)
    lastModified = models.DateTimeField(_('Last Modified Date'), auto_now=True)

    @property
    def grossTotal(self):
        return self.items.annotate(
            totalPrice=F('quantity')*F('item__price')
        ).aggregate(total=Sum('totalPrice')).get('total', 0) or 0

    def submitOrder(self, invoice=None, **kwargs):
        if self.status == self.OrderStatus.cancelled:
            # Orders that have already been cancelled are ignored.
            return
        if self.status == self.OrderStatus.unsubmitted:
            self.status = self.OrderStatus.submitted

        if invoice and self.invoice != invoice:
            raise ValidationError(_('Invalid invoice for submission'))
        elif invoice:
            self.invoice = invoice
        else:
            submissionUser = kwargs.pop('submissionUser', None)
            collectedByUser = kwargs.pop('collectedByUser', None)

            if not self.invoice:
                self.invoice = Invoice(
                    firstName=kwargs.pop('firstName', None),
                    lastName=kwargs.pop('lastName', None),
                    email=kwargs.pop('email', None),
                    grossTotal=self.grossTotal,
                    total=kwargs.pop('priceWithDiscount', self.grossTotal),
                    submissionUser=submissionUser,
                    collectedByUser=collectedByUser,
                    buyerPaysSalesTax=False,
                    status=kwargs.pop('status', Invoice.PaymentStatus.unpaid),
                    data=kwargs,
                )
                self.invoice.save()
        self.save()

    def cancelOrder(self):
        ''' TODO: Handle invoice update when an order is cancelled. '''
        self.status = self.OrderStatus.cancelled
        self.save()

        for item in self.items:
            item.unlinkInvoice()

    class Meta:
        verbose_name = _('Merchandise order')
        verbose_name_plural = _('Merchandise orders')
        constraints = (
            CheckConstraint(
                check=(
                    Q(status='UN') |
                    Q(invoice__isnull=False)
                ),
                name='submitted_has_invoice',
            ),
        )


class MerchOrderItem(models.Model):
    '''
    An individual item selected for purchase.  Notice that all of the details of
    pricing are handled by the invoice item it's associated with, not the item
    ordered itself.    
    '''
    order = models.ForeignKey(
        MerchOrder, on_delete=models.CASCADE, related_name='items',
    )

    item = models.ForeignKey(
        MerchItemVariant, verbose_name=_('Item'), on_delete=models.CASCADE,
        related_name='orders'
    )

    invoiceItem = models.OneToOneField(
        InvoiceItem, on_delete=models.SET_NULL, null=True, blank=True,
        help_text=_(
            'All submitted merchandise orders must be associated with an invoice.'
        )
    )

    quantity = models.PositiveIntegerField(
        _('Quantity'), default=1,
    )

    @property
    def grossTotal(self):
        return self.quantity * self.item.price

    def linkInvoice(self, update=True):
        '''
        If an order's contents are created or modified, this method ensures that
        the corresponding invoice items exist and that the totals are updated
        accordingly.
        '''
        newTotal = self.grossTotal
        invoice = self.order.invoice

        if (
            invoice and self.invoiceItem and self.invoiceItem.invoice != invoice
        ):
            raise ValidationError(_('Invoice item does not match order invoice'))

        if (
            update and self.invoiceItem and (
                self.invoiceItem.grossTotal != newTotal or
                self.invoiceItem.total != newTotal
            )
        ):
            self.invoiceItem.grossTotal = newTotal
            self.invoiceItem.total = newTotal
            self.invoiceItem.save()
        elif not self.invoiceItem and invoice:
            new_item = InvoiceItem(
                invoice=invoice,
                description=self.item.fullName,
                grossTotal=newTotal,
                total=newTotal,
            )
            new_item.save()
            self.invoiceItem = new_item
            self.save()

    def unlinkInvoice(self):
        '''
        If an order is cancelled, then the corresponding invoice items are
        removed from the invoice.  The merch order item remains so that the
        details of the cancelled order remain available.
        '''
        self.invoiceItem.delete()


    class Meta:
        verbose_name = _('Merchandise order item')
        verbose_name_plural = _('Merchandise order items')
        # TODO: Add this constraint once CheckConstraints on foreign keys
        # are supported in Django 3.1.
        '''
        constraints = (
            CheckConstraint(
                check=(
                    Q(order__status=MerchOrder.OrderStatus.unsubmitted) |
                    Q(order__status=MerchOrder.OrderStatus.cancelled) |
                    Q(invoiceItem__isnull=False)
                ),
                name='submitted_item_has_invoice_item',
            ),
        )
        '''
        

class DoorRegisterMerchPluginModel(CMSPlugin):
    '''
    This model holds information on a set of merchandise items that are sold
    at the door.
    '''

    title = models.CharField(
        _('Custom list title'), max_length=250, default=_('Merchandise'),
        blank=True
    )

    categories = models.ManyToManyField(
        MerchItemCategory, blank=True,
        verbose_name=_('Limit to merchandise categories'),
        help_text=_('Leave blank for no restriction'),
    )

    separateVariants = models.BooleanField(
        _('Display item variants as separate items'), default=False
    )

    displaySoldOut = models.BooleanField(
        _('Display items and variants that are sold out'), default=False
    )

    requireFullRegistration = models.BooleanField(
        _('Require full registration'), blank=True, default=True,
        help_text=_(
            'If checked, then the user will be sent to the second page of the ' +
            'registration process to provide name and email. Particular payment ' +
            'methods may also require the full registration process.'
        )
    )

    paymentMethods = models.ManyToManyField(
        DoorRegisterPaymentMethod,
        verbose_name=_('Payment Methods'),
        help_text=_(
            'If you would like separate buttons for individual payment methods, ' +
            'then select them here.  If left blank, a single button will be shown ' +
            'and no payment method will be specified.'
        ),
        blank=True,
    )

    template = models.CharField(_('Plugin template'), max_length=250, null=True, blank=True)

    cssClasses = models.CharField(
        _('Custom CSS classes'), max_length=250, null=True, blank=True,
        help_text=_('Classes are applied to surrounding &lt;div&gt;')
    )

    def getMerch(self):
        filters = Q(disabled=False)

        categories = self.categories.all()
        if categories:
            filters = filters & Q(category__in=categories)
        
        if not self.displaySoldOut:
            filters = filters & Q(item_variant__soldOut=False)
        
        return MerchItem.objects.filter(filters).distinct()
