from django.db import models
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import random
import string

from danceschool.core.models import (
    CustomerGroup, Customer, Invoice,
    ClassDescription, DanceTypeLevel, SeriesCategory, PublicEventCategory,
    EventSession, Event
)


class VoucherCategory(models.Model):
    name = models.CharField(_('Name'), max_length=80, unique=True)
    description = models.TextField(_('Description'), null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Voucher category')
        verbose_name_plural = _('Voucher categories')


class Voucher(models.Model):
    # unique identifier
    voucherId = models.CharField(
        _('Voucher Code'), max_length=100, unique=True,
        validators=[RegexValidator(regex=r'^[a-zA-Z\-_0-9]+$')]
    )

    # i.e. Social Living April 2013
    name = models.CharField(
        _('Name'), max_length=80,
        help_text=_(
            'Give a descriptive name that will be used when a customer applies the voucher.'
        )
    )

    # i.e. LivingSocial.  This is for categorical convenience only.
    category = models.ForeignKey(
        VoucherCategory, verbose_name=_('Category'), null=True,
        on_delete=models.SET_NULL,
    )

    # Optional description for when vouchers are given in special cases.
    description = models.CharField(
        _('Description (optional)'), null=True, blank=True, max_length=200,
        help_text=_('For internal use only')
    )

    # i.e. $45
    originalAmount = models.FloatField(
        _('Original Amount'),
        help_text=_('Enter the original amount of the voucher here.'),
        validators=[MinValueValidator(0)]
    )
    refundAmount = models.FloatField(
        _('Refunded Amount'), default=0,
        help_text=_(
            'When a refund is processed through Paypal, this should' +
            ' automatically update.  Otherwise it should not need to be changed.'
        )
    )

    # i.e. $2 - For tracking new students.  If null,
    # then there is no limit imposed.
    maxAmountPerUse = models.FloatField(
        _('Max. Amount Per Use'), null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text=_(
            'If specified, this will limit the size of a repeated-use voucher.' +
            '  If unspecified, there is no limit.  Be sure to specify this for' +
            ' publicly advertised voucher codes.'
        )
    )

    beforeTax = models.BooleanField(
        _('Voucher applied before tax'), default=True,
        help_text=_(
            'Voucher codes that are used as discounts or promotions are ' +
            'usually subtracted from the total price before any applicable ' +
            'sales tax is calculated, while gift certificates are subtracted ' +
            'from the after-tax total price.')
    )

    # i.e. For Groupon and LivingSocial, these are single use
    singleUse = models.BooleanField(_('Single Use'), default=False)

    # If a customer has been with us before, we don't want them to be able to use
    # LivingSocial or Groupon
    forFirstTimeCustomersOnly = models.BooleanField(_('For First-Time Customers Only'), default=False)

    # If a customer is new, we don't want them to be able to use vouchers designed
    # existing customers, like generic referral vouchers.
    forPreviousCustomersOnly = models.BooleanField(_('For Previous Customers Only'), default=False)

    # Some vouchers should only be used at the door (e.g. internal price
    # adjustment vouchers that we don't want anyone to be able to use unless they
    # are logged in).
    doorOnly = models.BooleanField(_('At-the-door Registrations Only'), default=False)

    # Keep track of when vouchers are created
    creationDate = models.DateTimeField(_('Creation Date'), auto_now_add=True)

    # If null, then there is no expiration date
    expirationDate = models.DateTimeField(_('Expiration Date'), null=True, blank=True)

    # Vouchers can be disabled manually with this field.
    disabled = models.BooleanField(
        _('Voucher Disabled'), default=False,
        help_text=_('Check this box to disable the voucher entirely.')
    )

    @classmethod
    def create_new_code(cls, **kwargs):
        '''
        Creates a new Voucher with a unique voucherId
        '''
        prefix = kwargs.pop('prefix', '')

        new = False
        while not new:
            # Standard is a ten-letter random string of uppercase letters
            random_string = ''.join(random.choice(string.ascii_uppercase) for z in range(10))
            if not Voucher.objects.filter(voucherId='%s%s' % (prefix, random_string)).exists():
                new = True

        return Voucher.objects.create(voucherId='%s%s' % (prefix, random_string), **kwargs)

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
        return (
            (self.originalAmount or 0) - (self.refundAmount or 0) -
            (self.voucheruse_set.filter(applied=True).aggregate(
                sum=Sum('amount')
            ).get('sum') or 0) +
            (self.vouchercredit_set.aggregate(sum=Sum('amount')).get('sum') or 0)
        )
    amountLeft = property(fget=getAmountLeft)
    amountLeft.fget.short_description = _('Amount remaining')

    def getMaxToUse(self):
        # If max amount per use is specified, use that, otherwise use amountLeft
        return min(
            self.amountLeft, self.maxAmountPerUse or self.amountLeft
        )

    maxToUse = property(fget=getMaxToUse)
    maxToUse.fget.short_description = _('Maximum amount available for next use')

    def validate(
        self, customer=None, events=None, payAtDoor=False, raise_errors=True,
        return_amount=False, validate_customer=True, validate_events=True
    ):
        '''
        Check whether this voucher is valid given optional parameters for the
        customer and an iterable (e.g. queryset or list) of events for which it
        may be used.  This method can also be specified to return the maximum
        amount for which a voucher may be used, which is just the smaller of its
        remaining balance and the max amount per its use.  By default, the method
        just raises a ValidationError if the voucher is not applicable
        (easiest for form field validation).  But, it can also be specified to return
        validation errors instead for downstream parsing, Ajax return, etc.
        Additionally, the method can be specified to skip validation of customer
        or event contents, which may be useful when a customer has not yet been
        specified or events have not yet been selected.
        '''

        errors = []
        warnings = []

        if events is None:
            events = Event.objects.none()

        if not hasattr(events, '__iter__'):
            raise ValueError(_('Invalid event list.'))
        if (type(customer) not in [Customer, type(None)]):
            raise ValueError(_('Invalid customer.'))

        if self.hasExpired:
            errors.append(
                ValidationError(_('Voucher has expired.'), code='expired')
            )

        # there is money left
        if self.amountLeft <= 0:
            errors.append(
                ValidationError(
                    _('There is no money left on this voucher.'),
                    code='no_remaining'
                )
            )

        # is not disabled
        if self.disabled:
            errors.append(
                ValidationError(_('This voucher has been disabled.'), code='disabled')
            )

        # not used (for single-use vouchers)
        if self.singleUse and self.voucheruse_set.filter(applied=True).count() > 0:
            errors.append(
                ValidationError(
                    _('This single-use voucher has already been used.'),
                    code='used'
                )
            )

        if self.doorOnly and not payAtDoor:
            errors.append(
                ValidationError(
                    _('This voucher can only be used for registration at the door.'),
                    code='door_only'
                )
            )

        # To avoid extraneous database calls, stop here if we're just going to
        # reject the voucher anyway.
        if errors and raise_errors:
            raise ValidationError(errors)

        # Only validate events contents if specified (default is True)
        if validate_events:
            # every series is either in the list or there is no list
            if self.classvoucher_set.exists():
                for s in events:
                    if not self.classvoucher_set.filter(
                        classDescription=s.classDescription
                    ).exists():
                        errors.append(
                            ValidationError(
                                _('This voucher can be only used for specific classes.'),
                                code='classvoucher_invalid'
                            )
                        )
            if self.dancetypevoucher_set.exists():
                for s in events:
                    if not self.dancetypevoucher_set.filter(
                        danceTypeLevel=s.classDescription.danceTypeLevel
                    ).exists():
                        errors.append(
                            ValidationError(
                                _('This voucher can be only used for specific classes.'),
                                code='dancetypevoucher_invalid'
                            )
                        )
            if self.seriescategoryvoucher_set.exists():
                for s in events:
                    if not self.seriescategoryvoucher_set.filter(seriesCategory=s.category).exists():
                        errors.append(
                            ValidationError(
                                _('This voucher can be only used for specific classes.'),
                                code='seriescategoryvoucher_invalid'
                            )
                        )
            if self.publiceventcategoryvoucher_set.exists():
                for s in events:
                    if not self.publiceventcategoryvoucher_set.filter(
                        publicEventCategory=s.category
                    ).exists():
                        errors.append(
                            ValidationError(
                                _('This voucher can be only used for specific events.'),
                                code='publiceventcategoryvoucher_invalid'
                            )
                        )
            if self.sessionvoucher_set.exists():
                for s in events:
                    if not self.sessionvoucher_set.filter(session=s.session).exists():
                        errors.append(
                            ValidationError(
                                _('This voucher can be only used for specific classes or events.'),
                                code='sessionvoucher_invalid'
                            )
                        )
        elif (
            self.classvoucher_set.exists() or
            self.dancetypevoucher_set.exists() or
            self.seriescategoryvoucher_set.exists() or
            self.publiceventcategoryvoucher_set.exists() or
            self.sessionvoucher_set.exists()
        ):
            warnings.append({
                'code': 'event_restrictions',
                'message': _('This voucher can be only used for specific classes or events.')
            })

        # Only validate events contents if specified (default is True)
        if validate_customer:
            # customer is either in the list or there is no list
            if not self.isValidForAnyCustomer:
                if not customer:
                    errors.append(
                        ValidationError(
                            _('This voucher is associated with a specific customer or customer group.'),
                            code='no_customer_specified'
                        )
                    )

                cvs = self.customervoucher_set.all()
                cgvs = self.customergroupvoucher_set.all()

                if cvs.exists() and not cvs.filter(customer=customer).exists():
                    errors.append(
                        ValidationError(
                            _('This voucher is associated with a specific customer.'),
                            code='customer_invalid'
                        )
                    )
                elif cgvs.exists() and not cgvs.filter(group__in=customer.groups.all()).exists():
                    errors.append(
                        ValidationError(
                            _('This voucher is associated with a specific customer group.'),
                            code='customergroup_invalid'
                        )
                    )

            if self.forFirstTimeCustomersOnly and customer and customer.numEventRegistrations > 0:
                errors.append(
                    ValidationError(
                        _('This voucher can only be used by first time customers.'),
                        code='not_first_time_customer'
                    )
                )

            if self.forPreviousCustomersOnly and (not customer or customer.numEventRegistrations == 0):
                errors.append(
                    ValidationError(
                        _(
                            'This voucher can only be used by existing customers.' +
                            '  If you are an existing customer, be sure to register' +
                            ' with the same email address that you have used previously.'
                        ),
                        code='not_existing_customer',
                    )
                )
        elif not self.isValidForAnyCustomer:
            warnings.append({
                'code': 'customer_restrictions',
                'message': _(
                    'This voucher is associated with a specific customer or customer group.'
                )
            })

        # If there were errors and we are supposed to raise them, then no need
        # to proceed further.
        if errors and raise_errors:
            raise ValidationError(errors)

        retval = {
            'name': self.name,
            'id': self.voucherId,
            'status': 'valid',
            'beforeTax': self.beforeTax,
            'warnings': warnings,
        }

        if errors:
            retval.update({
                'status': 'invalid',
                'errors': [{'code': x.code, 'message': ';'.join(x.messages)} for x in errors]
            })
        elif return_amount and retval.get('status', None) == 'valid':
            retval['available'] = self.maxToUse

        return retval

    def __str__(self):
        return self.name + " " + str(self.id)

    class Meta:
        verbose_name = _('Voucher')
        verbose_name_plural = _('Vouchers')
        permissions = (
            (
                'generate_and_email_vouchers',
                _('Can generate and email vouchers using the quick voucher email view.')
            ),
        )


class VoucherReferralDiscount(models.Model):
    referrerVoucher = models.ForeignKey(
        Voucher, related_name="VoucherReferralDiscountForReferrer",
        verbose_name=_('Referrer voucher'), on_delete=models.CASCADE,
    )
    referreeVoucher = models.ForeignKey(
        Voucher, related_name="voucherreferralDiscountForReferree",
        verbose_name=_('Referree voucher'), on_delete=models.CASCADE
    )
    referrerBonus = models.FloatField(_('Amount awarded to referrer'))

    class Meta:
        verbose_name = _('Voucher referral discount')
        verbose_name_plural = _('Voucher referral discounts')


class VoucherUse(models.Model):
    voucher = models.ForeignKey(
        Voucher, verbose_name=_('Voucher'), on_delete=models.CASCADE,
    )
    invoice = models.ForeignKey(
        Invoice, verbose_name=_('Invoice'), on_delete=models.CASCADE,
    )
    amount = models.FloatField(_('Amount'), validators=[MinValueValidator(0)])

    beforeTax = models.BooleanField(
        _('Voucher applied before tax'), default=True,
    )

    notes = models.CharField(_('Notes'), max_length=100, null=True, blank=True)
    creationDate = models.DateTimeField(_('Date of use'), auto_now_add=True, null=True)
    applied = models.BooleanField(_('Use finalized'), default=False)

    class Meta:
        verbose_name = _('Voucher use')
        verbose_name_plural = _('Voucher uses')


class DanceTypeVoucher(models.Model):
    danceTypeLevel = models.ForeignKey(
        DanceTypeLevel, verbose_name=_('Dance Type/Level'),
        on_delete=models.CASCADE,
    )
    voucher = models.ForeignKey(
        Voucher, verbose_name=_('Voucher'), on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = _('Dance type/level voucher restriction')
        verbose_name_plural = _('Dance type/level voucher restrictions')


class ClassVoucher(models.Model):
    classDescription = models.ForeignKey(
        ClassDescription, verbose_name=_('Class Type (Description)'), on_delete=models.CASCADE,
    )
    voucher = models.ForeignKey(
        Voucher, verbose_name=_('Voucher'), on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = _('Class-specific voucher restriction')
        verbose_name_plural = _('Class-specific voucher restrictions')


class SeriesCategoryVoucher(models.Model):
    seriesCategory = models.ForeignKey(
        SeriesCategory, verbose_name=_('Series Category'), on_delete=models.CASCADE
    )
    voucher = models.ForeignKey(
        Voucher, verbose_name=_('Voucher'), on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = _('Series category-specific voucher restriction')
        verbose_name_plural = _('Series category-specific voucher restrictions')


class PublicEventCategoryVoucher(models.Model):
    publicEventCategory = models.ForeignKey(
        PublicEventCategory, verbose_name=_('Public Event Category'),
        on_delete=models.CASCADE
    )
    voucher = models.ForeignKey(
        Voucher, verbose_name=_('Voucher'), on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = _('Public event category-specific voucher restriction')
        verbose_name_plural = _('public event Category-specific voucher restrictions')


class SessionVoucher(models.Model):
    session = models.ForeignKey(
        EventSession, verbose_name=_('Event Session'), on_delete=models.CASCADE
    )
    voucher = models.ForeignKey(
        Voucher, verbose_name=_('Voucher'), on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = _('Session-specific voucher restriction')
        verbose_name_plural = _('Session-specific voucher restrictions')


class CustomerGroupVoucher(models.Model):
    group = models.ForeignKey(
        CustomerGroup, verbose_name=_('Customer group'), on_delete=models.CASCADE
    )
    voucher = models.ForeignKey(
        Voucher, verbose_name=_('Voucher'), on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = _('Group-specific voucher restriction')
        verbose_name_plural = _('Group-specific voucher restrictions')


class CustomerVoucher(models.Model):
    customer = models.ForeignKey(
        Customer, verbose_name=_('Customer'), on_delete=models.CASCADE
    )
    voucher = models.ForeignKey(
        Voucher, verbose_name=_('Voucher'), on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = _('Customer-specific voucher restriction')
        verbose_name_plural = _('Customer-specific voucher restrictions')


class VoucherCredit(models.Model):
    voucher = models.ForeignKey(
        Voucher, verbose_name=_('Voucher'), on_delete=models.CASCADE
    )
    amount = models.FloatField(_('Amount'), validators=[MinValueValidator(0)])
    description = models.TextField(_('Description'), null=True, blank=True)
    creationDate = models.DateTimeField(_('Date of credit'), auto_now_add=True, null=True)

    class Meta:
        verbose_name = _('Voucher credit')
        verbose_name_plural = _('Voucher credits')


class VoucherReferralDiscountUse(models.Model):
    voucherReferralDiscount = models.ForeignKey(
        VoucherReferralDiscount, verbose_name=_('Voucher referral discount'),
        on_delete=models.CASCADE
    )
    voucherUse = models.ForeignKey(
        VoucherUse, verbose_name=_('Voucher use'), on_delete=models.CASCADE
    )
    voucherCredit = models.ForeignKey(
        VoucherCredit, verbose_name=_('Voucher credit'), on_delete=models.CASCADE
    )
    creationDate = models.DateTimeField(_('Date of use'), auto_now_add=True, null=True)

    class Meta:
        verbose_name = _('Use of voucher referral discount')
        verbose_name_plural = _('Uses of voucher referral discounts')
