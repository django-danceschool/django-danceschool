from django.db import models
from django.db.models import Q, F, Sum, Case, When, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.core.validators import MinValueValidator, RegexValidator
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from filer.fields.image import FilerImageField
from cms.models.pluginmodel import CMSPlugin
from datetime import timedelta

from danceschool.core.models import Invoice, InvoiceItem
from danceschool.core.constants import getConstant
from danceschool.register.models import RegisterPaymentMethod

from .managers import MerchOrderManager


def get_defaultSalesTaxRate():
    ''' Callable for default used by MerchItem class '''
    return getConstant('registration__merchSalesTaxRate')


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

    def save(self, *args, **kwargs):
        ''' Update the sold out status of the item variant. '''
        self.updateSoldOut(commit=False)
        super().save(*args, **kwargs)

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

    def delete(self, *args, **kwargs):
        '''
        Quantity adjustments cannot be deleted. Another quantity adjustment
        is instead submitted negating the quantity of this adjustment.
        '''
        new_adjustment = MerchQuantityAdjustment(
            variant=self.variant, amount = -1*self.amount
        )
        new_adjustment.save()

    def __str__(self):
        return str(_('Inventory adjustment for {itemName}, {submissionDate}'.format(
            itemName=self.variant.fullName, submissionDate=self.submissionDate)
        ))


class MerchOrder(models.Model):

    class OrderStatus(models.TextChoices):
        unsubmitted = ('UN', _('Not yet submitted'))
        submitted = ('SU', _('Submitted'))
        approved = ('AP', _('Approved for fulfillment'))
        fulfilled = ('F', _('Fulfilled'))
        cancelled = ('C', _('Cancelled'))
        fullRefund = ('R', _('Refunded in full'))

    status = models.CharField(
        _('Order status'), max_length=2, choices=OrderStatus.choices,
        default=OrderStatus.unsubmitted,
        help_text=_(
            'Use the order status to keep track of submission, processing, ' +
            'shipment (if applicable), and fulfillment.'
        )
    )

    invoice = models.OneToOneField(
        Invoice, on_delete=models.CASCADE, related_name='merchOrder',
        help_text=_(
            'All merchandise orders must be associated with an invoice.'
        )
    )

    creationDate = models.DateTimeField(_('Creation Date'), auto_now_add=True)
    lastModified = models.DateTimeField(_('Last Modified Date'), auto_now=True)

    data = models.JSONField(_('Additional data'), default=dict, blank=True)

    # This custom manager prevents deletion of MerchOrders that are not
    # unsubmitted, even using queryset methods.
    objects = MerchOrderManager()

    @property
    def grossTotal(self):
        return self.items.annotate(
            unitPrice=Case(
                When(item__price__isnull=True, then=F('item__item__defaultPrice')),
                default=F('item__price'), output_field=models.FloatField()
            ),
            totalPrice=ExpressionWrapper(
                F('quantity')*F('unitPrice'), output_field=models.FloatField()
            )
        ).aggregate(total=Sum('totalPrice')).get('total', 0) or 0

    @property
    def itemsEditable(self):
        ''' Only unsubmitted orders can have items added or removed. '''
        return self.status == self.OrderStatus.unsubmitted

    def getOtherInvoiceDetails(self):
        '''
        Return a dictionary with details on the sum of totals for non-order
        items on the invoice associated with this order.
        '''

        if not getattr(self, 'invoice', None):
            return {}
        return self.invoice.invoiceitem_set.exclude(
            id__in=self.items.values_list(
                'invoiceItem', flat=True
            )
        ).aggregate(
            grossTotal=Coalesce(Sum('grossTotal'), 0),
            total=Coalesce(Sum('total'), 0),
            adjustments=Coalesce(Sum('adjustments'), 0),
            taxes=Coalesce(Sum('taxes'), 0),
            fees=Coalesce(Sum('fees'), 0),
        )

    def link_invoice(self, update=True, **kwargs):
        '''
        If an invoice does not already exist for this order,
        then create one.  If an update is requested, then ensure that all
        details of the invoice match the order.
        Return the linked invoice.
        '''

        submissionUser = kwargs.pop('submissionUser', None)
        collectedByUser = kwargs.pop('collectedByUser', None)
        status = kwargs.pop('status', None)
        expirationDate = kwargs.pop('expirationDate', None)
        default_expiry = timezone.now() + timedelta(minutes=getConstant('registration__sessionExpiryMinutes'))


        if not getattr(self, 'invoice', None):

            invoice_kwargs = {
                'firstName': kwargs.pop('firstName', None),
                'lastName': kwargs.pop('lastName', None),
                'email': kwargs.pop('email', None),
                'grossTotal': self.grossTotal,
                'total': self.grossTotal,
                'submissionUser': submissionUser,
                'collectedByUser': collectedByUser,
                'buyerPaysSalesTax': getConstant('registration__buyerPaysSalesTax'),
                'data': kwargs,
            }

            if (
                (not status or status == Invoice.PaymentStatus.preliminary) and
                (self.status == self.OrderStatus.unsubmitted)
            ):
                invoice_kwargs.update({
                    'status': Invoice.PaymentStatus.preliminary,
                    'expirationDate': expirationDate or default_expiry
                })
            elif not status:
                invoice_kwargs.update({
                    'status': Invoice.PaymentStatus.unpaid,
                })

            new_invoice = Invoice(**invoice_kwargs)
            new_invoice.save()
            self.invoice = new_invoice
        elif update:
            needs_update = False

            other_details = self.getOtherInvoiceDetails()

            if kwargs.get('firstName', None):
                self.invoice.firstName = kwargs.get('firstName', None)
                needs_update = True
            if kwargs.get('lastName', None):
                self.invoice.lastName = kwargs.get('lastName', None)
                needs_update = True
            if kwargs.get('email', None):
                self.invoice.email = kwargs.get('email', None)
                needs_update = True

            if status and status != self.invoice.status:
                self.invoice.status = status
                needs_update = True

            if (
                self.invoice.grossTotal != self.grossTotal + other_details.get('grossTotal',0)
            ):
                self.invoice.grossTotal = self.grossTotal + other_details.get('grossTotal', 0)
                needs_update = True

            if (
                expirationDate and expirationDate != self.invoice.expirationDate
                and self.invoice.status == Invoice.PaymentStatus.preliminary
            ):
                self.invoice.expirationDate = expirationDate
                needs_update = True
            elif self.invoice.status != Invoice.PaymentStatus.preliminary:
                self.invoice.expirationDate = None
                needs_update = True

            if needs_update:
                self.invoice.save()

        return self.invoice

    def save(self, *args, **kwargs):
        '''
        Before saving this order, ensure that an associated invoice exists.
        If an invoice already exists, then update the invoice if anything
        requires updating.
        '''
        link_kwargs = {
            'submissionUser': kwargs.pop('submissionUser', None),
            'collectedByUser': kwargs.pop('collectedByUser', None),
            'status': kwargs.pop('status', None),
            'expirationDate': kwargs.pop('expirationDate', None),
            'update': kwargs.pop('updateInvoice', True),
        }

        self.invoice = self.link_invoice(**link_kwargs)
        super().save(*args, **kwargs)

        # Update the sold out status of the associated item variants if needed.
        if (
            self.status not in [
                self.OrderStatus.unsubmitted, self.OrderStatus.cancelled
            ] and self.status != self.__initial_status
        ):
            variants = [x.item for x in self.items.all()]
            for variant in variants:
                variant.updateSoldOut()

    def delete(self, *args, **kwargs):
        '''
        Only unsubmitted orders can be deleted.  Orders can also only be cancelled
        if money has not been collected on the invoice.  Otherwise, the order
        status needs to be changed via a refund on the invoice.
        '''
        if self.status == self.OrderStatus.unsubmitted:
            super().delete(*args, **kwargs)
        elif getattr(self.invoice, 'status') in [
            Invoice.PaymentStatus.needsCollection, Invoice.PaymentStatus.cancelled
        ]:
            self.status = self.OrderStatus.cancelled
            self.save()

    def __init__(self, *args, **kwargs):
        ''' Keep track of initial status in memory to detect status changes. '''
        super().__init__(*args, **kwargs)
        self.__initial_status = self.status

    class Meta:
        verbose_name = _('Merchandise order')
        verbose_name_plural = _('Merchandise orders')


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
        InvoiceItem, on_delete=models.CASCADE,
        help_text=_(
            'All merchandise orders must be associated with an invoice.'
        )
    )

    quantity = models.PositiveIntegerField(
        _('Quantity'), default=1,
    )

    @property
    def grossTotal(self):
        return self.quantity * self.item.getPrice()

    def link_invoice_item(self, update=True, **kwargs):
        '''
        If an order's contents are created or modified, this method ensures that
        the corresponding invoice items exist and that the totals are updated
        accordingly.
        '''
        newTotal = self.grossTotal
        invoice = self.order.invoice
        invoiceItem = self.invoiceItem

        if (
            invoice and invoiceItem and invoiceItem.invoice != invoice
        ):
            raise ValidationError(_('Invoice item does not match order invoice'))

        if (
            update and invoiceItem and (
                invoiceItem.grossTotal != newTotal or
                invoiceItem.total != newTotal
            )
        ):
            invoiceItem.grossTotal = newTotal
            invoiceItem.total = newTotal
            invoiceItem.taxRate = self.item.item.salesTaxRate
            invoiceItem.calculateTaxes()
            invoiceItem.save()
        elif not invoiceItem and invoice:
            new_item = InvoiceItem(
                invoice=invoice,
                description=self.item.fullName,
                grossTotal=newTotal,
                total=newTotal,
                taxRate=self.item.item.salesTaxRate
            )
            new_item.calculateTaxes()
            new_item.save()
            self.invoiceItem = new_item
            self.save()
        return self.invoiceItem

    def save(self, *args, **kwargs):
        restrictStatus = kwargs.pop('restrictStatus', True)
        if self.order.itemsEditable or not restrictStatus:
            self.invoiceItem = self.link_invoice_item(
                update=kwargs.pop('updateInvoiceItem', True)
            )
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        restrictStatus = kwargs.pop('restrictStatus', True)
        if self.order.itemsEditable or not restrictStatus:
            super().delete(*args, **kwargs)

    class Meta:
        verbose_name = _('Merchandise order item')
        verbose_name_plural = _('Merchandise order items')
        unique_together = ('item', 'order',)
        

class RegisterMerchPluginModel(CMSPlugin):
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

    autoFulfill = models.BooleanField(
        _('Automatically mark order as fulfilled upon payment.'),
        default=False, help_text=_(
            'If checked, and if all items added to this merch order also ' +
            'this option check, then the order will automatically be marked ' + 
            'as fulfilled when the invoice is finalized. Useful for ' +
            'merchandise that is sold immediately at the point-of-sale.'
        )
    )

    paymentMethods = models.ManyToManyField(
        RegisterPaymentMethod,
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

    def copy_relations(self, oldinstance):
        super().copy_relations(oldinstance)

        # Delete existing choice instances to avoid duplicates, then duplicate
        # choice instances from the old plugin instance.  Following Django CMS
        # documentation.
        self.categories.all().delete()
        self.paymentMethods.all().delete()

        for choice in oldinstance.categories.all():
            choice.pk = None
            choice.registermerchpluginmodel = self
            choice.save()

        for choice in oldinstance.paymentMethods.all():
            choice.pk = None
            choice.registermerchpluginmodel = self
            choice.save()
