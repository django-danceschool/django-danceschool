from django.db import models
from django.core.validators import MinValueValidator
from django.utils.translation import ugettext_lazy as _

from djchoices import DjangoChoices, ChoiceItem
from calendar import day_name
from collections import namedtuple

from danceschool.core.models import PricingTier, DanceTypeLevel, Registration, TemporaryRegistration, Customer, CustomerGroup


class PointGroup(models.Model):
    name = models.CharField(_('Name'),max_length=50,unique=True,help_text=_('Give this pricing tier point group a name (e.g. \'Regular Series Class Hours\')'))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Point group type')
        verbose_name_plural = _('Point group types')


class PricingTierGroup(models.Model):
    '''
    Because we want to keep the discounts app completely separable from the core app
    for schools that do not use discounting, this model serves as a go-between
    from the PricingTier objects of the core app to the PointGroup objects used
    in constructing discounts.
    '''
    group = models.ForeignKey(PointGroup,verbose_name=_('Point group'))
    pricingTier = models.OneToOneField(PricingTier,verbose_name=_('Pricing tier'))
    points = models.PositiveIntegerField(_('# of Points'),default=0)

    def __str__(self):
        return str(_('%s points for pricing tier %s' % (self.group.name, self.pricingTier.name)))

    class Meta:
        ''' Only one pricingtiergroup per pricingtier and group combo '''
        unique_together = (('pricingTier','group'),)
        verbose_name = _('Pricing tier point group')
        verbose_name_plural = _('Pricing tier point groups')


class DiscountCategory(models.Model):
    '''
    The discounts app allows one discount to be applied per category
    '''
    name = models.CharField(_('Category name'),max_length=30,unique=True)
    order = models.FloatField(
        _('Category order'),
        help_text=_('Discounts from categories with lower numbers are applied first.'),
        unique=True
    )
    cannotCombine = models.BooleanField(
        _('Cannot be combined'),
        help_text=_('If checked, then discounts in this category cannot be combined with any other type of discount.'),
        default=False,
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('order',)
        verbose_name = _('Discount category')
        verbose_name_plural = _('Discount categories')


class DiscountCombo(models.Model):

    # Choices of Discount Types
    class DiscountType(DjangoChoices):
        flatPrice = ChoiceItem('F',_('Exact Specified Price'))
        dollarDiscount = ChoiceItem('D',_('Dollar Discount from Regular Price'))
        percentDiscount = ChoiceItem('P',_('Percentage Discount from Regular Price'))
        addOn = ChoiceItem('A',_('Free Add-on Item (Can be combined with other discounts)'))

    # An applied discount may not apply to all items in a customer's
    # cart, so an instance of this class keeps track of the code
    # as well as the items applicable.  ItemTuples should be a series of 2-tuples.
    # For point-based discounts, the second position in the tuple represents what fraction of the
    # points were used from this item to match the discount (1 if the item was counted in its
    # entirety toward the discount). In cases where a discount does not count against an item entirely
    # (e.g. the 9 hours of class discount applied to three four-week classes), the full price for that
    # item will be calculated by multiplying the remaining fraction of points for that item (e.g. 75%
    # in the above example) against the regular (non-student, online registration) price for that item.
    # In practice, this means that a discount on the whole item will never be superceded by a discount
    # on a portion of the item as long as the percentage discounts for more point are always larger
    # than the discounts for fewer points (e.g. additional hours of class are cheaper).
    ApplicableDiscountCode = namedtuple('ApplicableDiscountCode',['code','items','itemTuples'])

    # Net allocated prices are optional, everything else is required.
    DiscountInfo = namedtuple('DiscountInfo',['code','net_price','discount_amount','net_allocated_prices'])
    DiscountInfo.__new__.__defaults__ = ([],)

    # A DiscountApplication contains a list of DiscountInfo tuples to be applied, along with an optional
    # total for ineligible items to be added to the discounted net price at the end.
    DiscountApplication = namedtuple('DiscountApplication',['items','ineligible_total'])
    DiscountApplication.__new__.__defaults__ = ([],0)

    name = models.CharField(_('Name'),max_length=50,unique=True,help_text=_('Give this discount combination a name (e.g. \'Two 4-week series\')'))
    active = models.BooleanField(_('Active'),default=True,help_text=_('Uncheck this to \'turn off\' this discount'))
    category = models.ForeignKey(
        DiscountCategory,verbose_name=_('Discount category'),
        help_text=_('One discount can be applied per category, and the order in which discounts are applied depends on the order parameter of the categories.')
    )

    # If null, then there is no expiration date
    expirationDate = models.DateTimeField(_('Expiration Date'), null=True,blank=True,help_text=_('Leave blank for no expiration.'))

    studentsOnly = models.BooleanField(verbose_name=_('Discount for HS/college/university students only'),default=False,help_text=_('Check this box to create student discounts.'))
    newCustomersOnly = models.BooleanField(verbose_name=_('Discount for New Customers only'),default=False)
    daysInAdvanceRequired = models.PositiveIntegerField(
        _('Must register __ days in advance'),
        null=True, blank=True,
        help_text=_(
            'For this discount to apply, all components must be satisfied by events that begin '
            'this many days in the future (measured from midnight of the date of registration). '
            'Leave blank for no restriction.'
        ),
    )
    firstXRegistered = models.PositiveSmallIntegerField(
        _('Only for first __ registrants'),
        null=True, blank=True,
        help_text=_(
            'For this discount to apply, all components must be satisfied by events that have fewer '
            'than this many individuals registered (including registrations in progress). '
            'Only one discount per category can be applied, so if you define tiered discounts '
            'in the same category, only the best available discount will be used.'
        )
    )

    discountType = models.CharField(_('Discount type'),max_length=1,help_text=_('Is this a flat price, a dollar amount discount, a \'percentage off\' discount, or a free add-on?'),choices=DiscountType.choices,default=DiscountType.dollarDiscount)

    # For flat price discounts
    onlinePrice = models.FloatField(_('Online price'),null=True,blank=True,validators=[MinValueValidator(0)])
    doorPrice = models.FloatField(_('At-the-door price'),null=True,blank=True,validators=[MinValueValidator(0)])

    # For 'dollars off' discounts
    dollarDiscount = models.FloatField(_('Amount of dollar discount'),null=True,blank=True,help_text=_('This amount will be subtracted from the customer\'s total (in currency units, e.g. dollars).'),validators=[MinValueValidator(0)])

    # For 'percentage off' discounts
    percentDiscount = models.FloatField(_('Amount of percentage discount'),null=True,blank=True,help_text=_('This percentage will be subtracted from the customer\'s total.'),validators=[MinValueValidator(0)])
    percentUniversallyApplied = models.BooleanField(_('Percentage discount is univerally applied'),default=False,help_text=_('If checked, then the percentage discount will be applied to all items in the order, not just the items that qualify the order for this discount combination (e.g. 20% off all registrations of three or more classes.'))

    def applyAndAllocate(self,allocatedPrices,tieredTuples,payAtDoor=False):
        '''
        This method takes an initial allocation of prices across events, and
        an identical length list of allocation tuples.  It applies the rule
        specified by this discount, allocates the discount across the listed
        items, and returns both the price and the allocation
        '''
        initial_net_price = sum([x for x in allocatedPrices])

        if self.discountType == self.DiscountType.flatPrice:
            # Flat-price for all applicable items (partial application for items which are
            # only partially needed to apply the discount).  Flat prices ignore any previous discounts
            # in other categories which may have been the best, but they only are applied if they are
            # lower than the price that would be feasible by applying those prior discounts alone.
            applicable_price = self.getFlatPrice(payAtDoor) or 0

            this_price = applicable_price \
                + sum([x[0].event.getBasePrice(payAtDoor=payAtDoor) * x[1] if x[1] != 1 else x[0].price for x in tieredTuples])

            # Flat prices are allocated equally across all events
            this_allocated_prices = [x * (this_price / initial_net_price) for x in allocatedPrices]

        elif self.discountType == self.DiscountType.dollarDiscount:
            # Discount the set of applicable items by a specific number of dollars (currency units)
            # Dollar discounts are allocated equally across all events.
            this_price = initial_net_price - self.dollarDiscount
            this_allocated_prices = [x * (this_price / initial_net_price) for x in allocatedPrices]

        elif self.discountType == DiscountCombo.DiscountType.percentDiscount:
            # Percentage off discounts, which may be applied to all items in the cart,
            # or just to the items that were needed to apply the discount

            if self.percentUniversallyApplied:
                this_price = \
                    initial_net_price * (1 - (max(min(self.percentDiscount or 0,100),0) / 100))
                this_allocated_prices = [x * (this_price / initial_net_price) for x in allocatedPrices]
            else:
                # Allocate the percentage discount based on the prior allocation from the prior category
                this_price = 0
                this_allocated_prices = []

                for idx, val in enumerate(tieredTuples):
                    this_val = (
                        allocatedPrices[idx] *
                        (1 - val[1]) * (1 - (max(min(self.percentDiscount or 0,100),0) / 100)) +
                        allocatedPrices[idx] * val[1]
                    )
                    this_allocated_prices.append(this_val)
                    this_price += this_val
        else:
            raise KeyError(_('Invalid discount type.'))

        if this_price < initial_net_price:
            # Ensure no negative prices
            this_price = max(this_price, 0)
            return self.DiscountInfo(self, this_price, initial_net_price - this_price, this_allocated_prices)

    def getFlatPrice(self,payAtDoor=False):
        '''
        Rather than embedding logic re: door pricing,
        other code can call this method.
        '''
        if self.discountType is not DiscountCombo.DiscountType.flatPrice:
            return None
        if payAtDoor:
            return self.doorPrice
        else:
            return self.onlinePrice

    def getComponentList(self):
        '''
        This function just returns a list with items that are supposed to
        be present in the the list multiple times as multiple elements
        of the list.  It simplifies checking whether a discount's conditions
        are satisfied.
        '''

        component_list = []

        for x in self.discountcombocomponent_set.all():
            for y in range(0,x.quantity):
                component_list += [x]

        component_list.sort(key=lambda x: x.quantity, reverse=True)
        return component_list

    def save(self, *args, **kwargs):
        '''
        Don't save any passed values related to a type of discount
        that is not the specified type
        '''

        if self.discountType != self.DiscountType.flatPrice:
            self.onlinePrice = None
            self.doorPrice = None

        if self.discountType != self.DiscountType.dollarDiscount:
            self.dollarDiscount = None

        if self.discountType != self.DiscountType.percentDiscount:
            self.percentDiscount = None
            self.percentUniversallyApplied = False

        super(DiscountCombo, self).save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Discount')
        verbose_name_plural = _('Discounts')


class DiscountComboComponent(models.Model):

    # For weekday-specific discounts
    DAYS_CHOICES = [(None,''),] + [(k,x) for k,x in enumerate(day_name)]

    discountCombo = models.ForeignKey(DiscountCombo,verbose_name=_('Discount'))

    pointGroup = models.ForeignKey(PointGroup,verbose_name=_('Pricing Tier Point Group'))

    allWithinPointGroup = models.BooleanField(verbose_name=_('Applies to all within Point Group'),help_text=_('If checked, then this discount applies to this quantity or more within the point group.  Use, for example, for all-in passes.'))

    quantity = models.PositiveSmallIntegerField(_('Quantity'),default=1)
    level = models.ForeignKey(DanceTypeLevel,null=True,blank=True,verbose_name=_('Dance type/level'))
    weekday = models.PositiveSmallIntegerField(_('Weekday'),choices=DAYS_CHOICES,blank=True,null=True,help_text=_('Leave this blank for no restriction on days of the week'))

    class Meta:
        verbose_name = _('Required component of discount')
        verbose_name_plural = _('Required components of discount')


class TemporaryRegistrationDiscount(models.Model):
    registration = models.ForeignKey(TemporaryRegistration,verbose_name=_('Temporary registration'))
    discount = models.ForeignKey(DiscountCombo,verbose_name=_('Discount'))
    discountAmount = models.FloatField(verbose_name=_('Amount of discount'),validators=[MinValueValidator(0)])

    class Meta:
        unique_together = ('registration', 'discount')
        verbose_name = _('Discount applied to temporary registration')
        verbose_name_plural = _('Discounts applied to temporary registrations')


class RegistrationDiscount(models.Model):
    registration = models.ForeignKey(Registration,verbose_name=_('Registration'))
    discount = models.ForeignKey(DiscountCombo,verbose_name=_('Discount'))
    discountAmount = models.FloatField(verbose_name=_('Amount of discount'),validators=[MinValueValidator(0)])

    class Meta:
        unique_together = ('registration', 'discount')
        verbose_name = _('Discount applied to registration')
        verbose_name_plural = _('Discounts applied to registrations')


class CustomerGroupDiscount(models.Model):
    ''' Some discounts are only available for specific customer groups '''
    group = models.ForeignKey(CustomerGroup,verbose_name=_('Customer group'))
    discountCombo = models.ForeignKey(DiscountCombo,verbose_name=_('Discount'))

    class Meta:
        verbose_name = _('Group-specific discount restriction')
        verbose_name_plural = _('Group-specific discount restrictions')


class CustomerDiscount(models.Model):
    ''' Some discounts are only available for specific customers. '''
    customer = models.ForeignKey(Customer,verbose_name=_('Customer'))
    discountCombo = models.ForeignKey(DiscountCombo,verbose_name=_('Discount'))

    class Meta:
        verbose_name = _('Customer-specific discount restriction')
        verbose_name_plural = _('Customer-specific discount restrictions')
