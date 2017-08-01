from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.core.validators import MinValueValidator
from django.utils.translation import ugettext_lazy as _

from djchoices import DjangoChoices, ChoiceItem
from calendar import day_name

from danceschool.core.models import PricingTier, DanceTypeLevel, Registration, TemporaryRegistration

'''
Discount models now have their own app.
'''


@python_2_unicode_compatible
class PointGroup(models.Model):
    name = models.CharField(_('Name'),max_length=50,unique=True,help_text=_('Give this pricing tier point group a name (e.g. \'Regular Series Class Hours\')'))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Point group type')
        verbose_name_plural = _('Point group types')


@python_2_unicode_compatible
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

    class Meta:
        ''' Only one pricingtiergroup per pricingtier and group combo '''
        unique_together = (('pricingTier','group'),)
        verbose_name = _('Pricing tier point group')
        verbose_name_plural = _('Pricing tier point groups')


@python_2_unicode_compatible
class DiscountCombo(models.Model):

    # Choices of Discount Types
    class DiscountType(DjangoChoices):
        flatPrice = ChoiceItem('F',_('Exact Specified Price'))
        dollarDiscount = ChoiceItem('D',_('Dollar Discount from Regular Price'))
        percentDiscount = ChoiceItem('P',_('Percentage Discount from Regular Price'))
        addOn = ChoiceItem('A',_('Free Add-on Item (Can be combined with other discounts)'))

    name = models.CharField(_('Name'),max_length=50,unique=True,help_text=_('Give this discount combination a name (e.g. \'Two 4-week series\')'))
    active = models.BooleanField(_('Active'),default=True,help_text=_('Uncheck this to \'turn off\' this discount'))

    newCustomersOnly = models.BooleanField(verbose_name=_('Discount for New Customers only'),default=False)

    discountType = models.CharField(_('Discount type'),max_length=1,help_text=_('Is this a flat price, a dollar amount discount, a \'percentage off\' discount, or a free add-on?'),choices=DiscountType.choices,default=DiscountType.dollarDiscount)

    # For flat price discounts
    onlineStudentPrice = models.FloatField(_('Online student price'),null=True,blank=True,validators=[MinValueValidator(0)])
    doorStudentPrice = models.FloatField(_('At-the-door student price'),null=True,blank=True,validators=[MinValueValidator(0)])
    onlineGeneralPrice = models.FloatField(_('Online general price'),null=True,blank=True,validators=[MinValueValidator(0)])
    doorGeneralPrice = models.FloatField(_('At-the-door general price'),null=True,blank=True,validators=[MinValueValidator(0)])

    # For 'dollars off' discounts
    dollarDiscount = models.FloatField(_('Amount of dollar discount'),null=True,blank=True,help_text=_('This amount will be subtracted from the customer\'s total (in currency units, e.g. dollars).'),validators=[MinValueValidator(0)])

    # For 'percentage off' discounts
    percentDiscount = models.FloatField(_('Amount of percentage discount'),null=True,blank=True,help_text=_('This percentage will be subtracted from the customer\'s total.'),validators=[MinValueValidator(0)])
    percentUniversallyApplied = models.BooleanField(_('Percentage discount is univerally applied'),default=False,help_text=_('If checked, then the percentage discount will be applied to all items in the order, not just the items that qualify the order for this discount combination (e.g. 20% off all registrations of three or more classes.'))

    def getFlatPrice(self,isStudent=False,payAtDoor=False):
        '''
        Rather than embedding logic re: student discounts and door pricing,
        other code can call this method.
        '''
        if self.discountType is not DiscountCombo.DiscountType.flatPrice:
            return None
        if isStudent and not payAtDoor:
            return self.onlineStudentPrice
        elif isStudent:
            return self.doorStudentPrice
        elif not payAtDoor:
            return self.onlineGeneralPrice
        else:
            return self.doorGeneralPrice

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
            self.onlineStudentPrice = None
            self.onlineGeneralPrice = None
            self.doorStudentPrice = None
            self.doorGeneralPrice = None

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
    registration = models.OneToOneField(TemporaryRegistration,verbose_name=_('Temporary registration'))
    discount = models.ForeignKey(DiscountCombo,verbose_name=_('Discount'))
    discountAmount = models.FloatField(verbose_name=_('Amount of discount'),validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = _('Discount applied to temporary registration')
        verbose_name_plural = _('Discounts applied to temporary registrations')


class RegistrationDiscount(models.Model):
    registration = models.OneToOneField(Registration,verbose_name=_('Registration'))
    discount = models.ForeignKey(DiscountCombo,verbose_name=_('Discount'))
    discountAmount = models.FloatField(verbose_name=_('Amount of discount'),validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = _('Discount applied to registration')
        verbose_name_plural = _('Discounts applied to registrations')
