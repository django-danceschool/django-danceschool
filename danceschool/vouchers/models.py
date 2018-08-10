from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone
import random
import string

from danceschool.core.models import CustomerGroup, Customer, Registration, TemporaryRegistration, ClassDescription, DanceTypeLevel


class VoucherCategory(models.Model):
    name = models.CharField(_('Name'),max_length=80,unique=True)
    description = models.TextField(_('Description'),null=True,blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Voucher category')
        verbose_name_plural = _('Voucher categories')


class Voucher(models.Model):
    # unique identifier
    voucherId = models.CharField(_('Voucher Code'),max_length=100,unique=True)

    # i.e. Social Living April 2013
    name = models.CharField(_('Name'),max_length=80,help_text=_('Give a descriptive name that will be used when a customer applies the voucher.'))

    # i.e. LivingSocial.  This is for categorical convenience only.
    category = models.ForeignKey(VoucherCategory,verbose_name=_('Category'),null=True)

    # Optional description for when vouchers are given in special cases.
    description = models.CharField(_('Description (optional)'),null=True,blank=True,max_length=200,help_text=_('For internal use only'))

    # i.e. $45
    originalAmount = models.FloatField(_('Original Amount'),help_text=_('Enter the original amount of the voucher here.'),validators=[MinValueValidator(0)])
    refundAmount = models.FloatField(_('Refunded Amount'),default=0,help_text=_('When a refund is processed through Paypal, this should automatically update.  Otherwise it should not need to be changed.'))

    # i.e. $2 - For tracking new students.  If null,
    # then there is no limit imposed.
    maxAmountPerUse = models.FloatField(_('Max. Amount Per Use'),null=True,blank=True,validators=[MinValueValidator(0)],help_text=_('If specified, this will limit the size of a repeated-use voucher.  If unspecified, there is no limit.  Be sure to specify this for publicly advertised voucher codes.'))

    # i.e. For Groupon and LivingSocial, these are single use
    singleUse = models.BooleanField(_('Single Use'),default=False)

    # If a customer has been with us before, we don't want them to be able to use
    # LivingSocial or Groupon
    forFirstTimeCustomersOnly = models.BooleanField(_('For First-Time Customers Only'), default=False)

    # If a customer is new, we don't want them to be able to use vouchers designed
    # existing customers, like generic referral vouchers.
    forPreviousCustomersOnly = models.BooleanField(_('For Previous Customers Only'), default=False)

    # Keep track of when vouchers are created
    creationDate = models.DateTimeField(_('Creation Date'),auto_now_add=True)

    # If null, then there is no expiration date
    expirationDate = models.DateTimeField(_('Expiration Date'), null=True,blank=True)

    # Vouchers can be disabled manually with this field.
    disabled = models.BooleanField(_('Voucher Disabled'),default=False,help_text=_('Check this box to disable the voucher entirely.'))

    @classmethod
    def create_new_code(cls,**kwargs):
        '''
        Creates a new Voucher with a unique voucherId
        '''
        prefix = kwargs.pop('prefix','')

        new = False
        while not new:
            # Standard is a ten-letter random string of uppercase letters
            random_string = ''.join(random.choice(string.ascii_uppercase) for z in range(10))
            if not Voucher.objects.filter(voucherId='%s%s' % (prefix, random_string)).exists():
                new = True

        return Voucher.objects.create(voucherId='%s%s' % (prefix, random_string),**kwargs)

    def getHasExpired(self):
        if self.expirationDate and timezone.now() > self.expirationDate:
            return True
        else:
            return False

    hasExpired = property(fget=getHasExpired)
    hasExpired.fget.short_description = _('Has Expired')

    def getIsValidForAnyCustomer(self):
        isvalid = (
            len(CustomerVoucher.objects.filter(voucher=self)) +
            len(CustomerGroupVoucher.objects.filter(voucher=self)) == 0
        )
        return isvalid

    isValidForAnyCustomer = property(fget=getIsValidForAnyCustomer)
    isValidForAnyCustomer.fget.short_description = _('Voucher is valid for any customer')

    def getIsValidForAnyClass(self):
        if self.dancetypevoucher_set.exists() or self.classvoucher_set.exists():
            return False
        return True

    isValidForAnyClass = property(fget=getIsValidForAnyClass)
    isValidForAnyClass.fget.short_description = _('Voucher is valid for any class')

    def getAmountLeft(self):
        amount = self.originalAmount - self.refundAmount
        uses = VoucherUse.objects.filter(voucher=self)
        for use in uses:
            amount -= use.amount

        credits = VoucherCredit.objects.filter(voucher=self)

        for credit in credits:
            amount += credit.amount

        return amount

    amountLeft = property(fget=getAmountLeft)
    amountLeft.fget.short_description = _('Amount remaining')

    def validateForCustomerAndSeriess(self,customer,seriess):
        # check whether it's expired

        if self.hasExpired:
            raise ValidationError(_('Voucher has expired.'))

        # not used
        if self.singleUse and len(VoucherUse.objects.filter(voucher=self)) > 0:
            raise ValidationError(_('Voucher has already been used.'))

        # there is money left
        if self.amountLeft <= 0:
            raise ValidationError(_('There is no money left on this voucher.'))

        # every series is either in the list or there is no list
        if self.classvoucher_set.exists():
            for s in seriess:
                if not self.classvoucher_set.filter(classDescription=s.classDescription).exists():
                    raise ValidationError(_('This voucher can be only used for specific classes.'))
        if self.dancetypevoucher_set.exists():
            for s in seriess:
                if not self.dancetypevoucher_set.filter(danceTypeLevel=s.classDescription.danceTypeLevel).exists():
                    raise ValidationError(_('This voucher can only be used for %(level)s classes' % {'level': s.classDescription.danceTypeLevel.name}))

        # is not disabled
        if self.disabled:
            raise ValidationError(_('This voucher has been disabled.'))

        # customer is either in the list or there is no list
        if not self.isValidForAnyCustomer:
            if not customer:
                raise ValidationError(_('This voucher is associated with a specific customer or customer group.'))

            cvs = CustomerVoucher.objects.filter(voucher=self)
            cgvs = CustomerGroupVoucher.objects.filter(voucher=self)

            if cvs.exists() and not cvs.filter(customer=customer).exists():
                raise ValidationError(_('This voucher is associated with a specific customer.'))
            elif cgvs.exists() and not cgvs.filter(group__in=customer.groups.all()).exists():
                raise ValidationError(_('This voucher is associated with a specific customer group.'))

        if self.forFirstTimeCustomersOnly and customer and customer.numClassSeries > 0:
            raise ValidationError(_('This voucher can only be used by first time customers.'))

        if self.forPreviousCustomersOnly and (not customer or customer.numClassSeries == 0):
            raise ValidationError(_('This voucher can only be used by existing customers.  If you are an existing customer, be sure to register with the same email address that you have used previously.'))

        # Otherwise, we are all set.
        return True

    def __str__(self):
        return self.name + " " + str(self.id)

    class Meta:
        verbose_name = _('Voucher')
        verbose_name_plural = _('Vouchers')


class VoucherReferralDiscount(models.Model):
    referrerVoucher = models.ForeignKey(Voucher,related_name="VoucherReferralDiscountForReferrer",verbose_name=_('Referrer voucher'))
    referreeVoucher = models.ForeignKey(Voucher,related_name="voucherreferralDiscountForReferree",verbose_name=_('Referree voucher'))
    referrerBonus = models.FloatField(_('Amount awarded to referrer'))

    class Meta:
        verbose_name = _('Voucher referral discount')
        verbose_name_plural = _('Voucher referral discounts')


class VoucherUse(models.Model):
    voucher = models.ForeignKey(Voucher,verbose_name=_('Voucher'))
    registration = models.ForeignKey(Registration,null=True,verbose_name=_('Registration'))
    amount = models.FloatField(_('Amount'),validators=[MinValueValidator(0)])
    notes = models.CharField(_('Notes'),max_length=100,null=True,blank=True)
    creationDate = models.DateTimeField(_('Date of use'),auto_now_add=True,null=True)

    class Meta:
        verbose_name = _('Voucher use')
        verbose_name_plural = _('Voucher uses')


class DanceTypeVoucher(models.Model):
    danceTypeLevel = models.ForeignKey(DanceTypeLevel,verbose_name=_('Dance Type/Level'))
    voucher = models.ForeignKey(Voucher,verbose_name=_('Voucher'))

    class Meta:
        verbose_name = _('Dance type/level voucher restriction')
        verbose_name_plural = _('Dance type/level voucher restrictions')


class ClassVoucher(models.Model):
    classDescription = models.ForeignKey(ClassDescription,verbose_name=_('Class Type (Description)'))
    voucher = models.ForeignKey(Voucher,verbose_name=_('Voucher'))

    class Meta:
        verbose_name = _('Class-specific voucher restriction')
        verbose_name_plural = _('Class-specific voucher restrictions')


class CustomerGroupVoucher(models.Model):
    group = models.ForeignKey(CustomerGroup,verbose_name=_('Customer group'))
    voucher = models.ForeignKey(Voucher,verbose_name=_('Voucher'))

    class Meta:
        verbose_name = _('Group-specific voucher restriction')
        verbose_name_plural = _('Group-specific voucher restrictions')


class CustomerVoucher(models.Model):
    customer = models.ForeignKey(Customer,verbose_name=_('Customer'))
    voucher = models.ForeignKey(Voucher,verbose_name=_('Voucher'))

    class Meta:
        verbose_name = _('Customer-specific voucher restriction')
        verbose_name_plural = _('Customer-specific voucher restrictions')


class VoucherCredit(models.Model):
    voucher = models.ForeignKey(Voucher,verbose_name=_('Voucher'))
    amount = models.FloatField(_('Amount'),validators=[MinValueValidator(0)])
    description = models.TextField(_('Description'),null=True, blank=True)
    creationDate = models.DateTimeField(_('Date of credit'),auto_now_add=True,null=True)

    class Meta:
        verbose_name = _('Voucher credit')
        verbose_name_plural = _('Voucher credits')


class TemporaryVoucherUse(models.Model):
    registration = models.ForeignKey(TemporaryRegistration,verbose_name=_('Registration'))
    voucher = models.ForeignKey(Voucher,verbose_name=_('Voucher'))
    amount = models.FloatField(_('Amount'),validators=[MinValueValidator(0)])
    creationDate = models.DateTimeField(_('Date of use'),auto_now_add=True,null=True)

    class Meta:
        verbose_name = _('Tentative voucher use')
        verbose_name_plural = _('Tentative voucher uses')


class VoucherReferralDiscountUse(models.Model):
    voucherReferralDiscount = models.ForeignKey(VoucherReferralDiscount,verbose_name=_('Voucher referral discount'))
    voucherUse = models.ForeignKey(VoucherUse,verbose_name=_('Voucher use'))
    voucherCredit = models.ForeignKey(VoucherCredit,verbose_name=_('Voucher credit'))
    creationDate = models.DateTimeField(_('Date of use'),auto_now_add=True,null=True)

    class Meta:
        verbose_name = _('Use of voucher referral discount')
        verbose_name_plural = _('Uses of voucher referral discounts')
