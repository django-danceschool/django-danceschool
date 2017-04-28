from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
import datetime

from danceschool.core.models import Customer, Registration, TemporaryRegistration, ClassDescription, DanceTypeLevel


@python_2_unicode_compatible
class VoucherCategory(models.Model):
    name = models.CharField(max_length=80,unique=True)
    description = models.TextField(null=True,blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = _('Voucher categories')


@python_2_unicode_compatible
class Voucher(models.Model):
    # unique identifier
    voucherId = models.CharField(_('Voucher Code'),max_length=100,unique=True)

    # i.e. Social Living April 2013
    name = models.CharField(max_length=80)

    # i.e. LivingSocial.  This is for categorical convenience only.
    category = models.ForeignKey(VoucherCategory,null=True)

    # Optional description for when vouchers are given in special cases.
    type = models.CharField(_('Description'),null=True,blank=True,max_length=200)

    # i.e. $45
    originalAmount = models.FloatField(_('Original Amount'),help_text=_('Enter the original amount of the voucher here.'),validators=[MinValueValidator(0)])
    refundAmount = models.FloatField(_('Refunded Amount'),default=0,help_text=_('When a refund is processed through Paypal, this should automatically update.  Otherwise it should not need to be changed.'))

    # i.e. $2 - For tracking new students.  If null,
    # then there is no limit imposed.
    maxAmountPerUse = models.FloatField(_('Max. Amount Per Use'),null=True,blank=True,validators=[MinValueValidator(0)])

    # i.e. For Groupon and LivingSocial, these are single use
    singleUse = models.BooleanField(_('Single Use'),default=True)

    # If a customer has been with us before, we don't want them to be able to use
    # LivingSocial or Groupon
    forFirstTimeCustomersOnly = models.BooleanField(_('For First-Time Customers Only'), default=False)

    # If a customer is new, we don't want them to be able to use vouchers designed
    # existing customers, like generic referral vouchers.
    forPreviousCustomersOnly = models.BooleanField(_('For Previous Customers Only'), default=False)

    # Keep track of when vouchers are created
    creationDate = models.DateTimeField(auto_now_add=True)

    # If null, then there is no expiration date
    expirationDate = models.DateTimeField(_('Expiration Date'), null=True,blank=True)

    # Vouchers can be disabled manually with this field.
    disabled = models.BooleanField(default=False)

    def getHasExpired(self):
        if self.expirationDate and datetime.datetime.now() > self.expirationDate:
            return True
        else:
            return False

    hasExpired = property(fget=getHasExpired)

    def getIsValidForAnyCustomer(self):
        isvalid = len(CustomerVoucher.objects.filter(voucher=self)) == 0
        return isvalid

    isValidForAnyCustomer = property(fget=getIsValidForAnyCustomer)

    def getIsValidForAnyClass(self):
        if self.dancetypevoucher_set.exists() or self.classvoucher_set.exists():
            return False
        return True

    isValidForAnyClass = property(fget=getIsValidForAnyClass)

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

        # customer is either in list or there is no list
        if not self.isValidForAnyCustomer and (not customer or not CustomerVoucher.objects.filter(voucher=self,customer=customer).exists()):
            raise ValidationError(_('This voucher is associated with a specific customer.'))

        if self.forFirstTimeCustomersOnly and customer and customer.numClassSeries > 0:
            raise ValidationError(_('This voucher can only be used by first time customers.'))

        if self.forPreviousCustomersOnly and (not customer or customer.numClassSeries == 0):
            raise ValidationError(_('This voucher can only be used by existing customers.  If you are an existing customer, be sure to register with the same email address that you have used previously.'))

        # Otherwise, we are all set.
        return True

    def __str__(self):
        return self.name + " " + str(self.id)


class VoucherReferralDiscount(models.Model):
    referrerVoucher = models.ForeignKey(Voucher,related_name="VoucherReferralDiscountForReferrer")
    referreeVoucher = models.ForeignKey(Voucher,related_name="voucherreferralDiscountForReferree")

    # TODO: Could come from a third voucher that's the source of the moolah?
    referrerBonus = models.FloatField()


class VoucherUse(models.Model):
    voucher = models.ForeignKey(Voucher)
    registration = models.ForeignKey(Registration,null=True)
    amount = models.FloatField(validators=[MinValueValidator(0)])
    notes = models.CharField(max_length=100,null=True,blank=True)
    creationDate = models.DateTimeField(auto_now_add=True,null=True)


class DanceTypeVoucher(models.Model):
    danceTypeLevel = models.ForeignKey(DanceTypeLevel,verbose_name=_('Dance Type/Level'))
    voucher = models.ForeignKey(Voucher)


class ClassVoucher(models.Model):
    classDescription = models.ForeignKey(ClassDescription,verbose_name=_('Class Type (Description)'))
    voucher = models.ForeignKey(Voucher)


class CustomerVoucher(models.Model):
    customer = models.ForeignKey(Customer)
    voucher = models.ForeignKey(Voucher)


class VoucherCredit(models.Model):
    voucher = models.ForeignKey(Voucher)
    amount = models.FloatField(validators=[MinValueValidator(0)])
    description = models.TextField(null=True, blank=True)
    creationDate = models.DateTimeField(auto_now_add=True,null=True)


class TemporaryVoucherUse(models.Model):
    registration = models.ForeignKey(TemporaryRegistration)
    voucher = models.ForeignKey(Voucher)
    amount = models.FloatField(validators=[MinValueValidator(0)])
    creationDate = models.DateTimeField(auto_now_add=True,null=True)


class VoucherReferralDiscountUse(models.Model):
    voucherReferralDiscount = models.ForeignKey(VoucherReferralDiscount)
    voucherUse = models.ForeignKey(VoucherUse)
    voucherCredit = models.ForeignKey(VoucherCredit)
    creationDate = models.DateTimeField(auto_now_add=True,null=True)
