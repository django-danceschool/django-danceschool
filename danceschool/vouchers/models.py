from django.apps import apps
from django.db import models
from django.db.models import Sum
from django.db.models.query import QuerySet, FlatValuesListIterable
from django.core.exceptions import ObjectDoesNotExist, ValidationError
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


# Used by Voucher methods to tell an argument that was not passed apart from
# one that was passed as None.
NOT_GIVEN = object()


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

    appliesToEntireInvoice = models.BooleanField(
        _('Can be used for anything on the invoice'), default=False,
        help_text=_(
            'If this voucher is restricted to specific classes or events, then '
            'by default it can only be used for registrations for those classes '
            'or events. If checked, then once there is such a registration, the '
            'voucher can be used for everything on the invoice, including other '
            'registrations and merchandise.'
        )
    )

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

    @property
    def isEventRestricted(self):
        ''' Is this voucher restricted to specific classes or events? '''
        return (
            self.classvoucher_set.exists() or
            self.dancetypevoucher_set.exists() or
            self.seriescategoryvoucher_set.exists() or
            self.publiceventcategoryvoucher_set.exists() or
            self.sessionvoucher_set.exists()
        )

    def eventQualifies(self, event):
        '''
        Can this voucher be used for a registration for the passed event?  An
        event qualifies if it meets every type of restriction that the voucher
        has (classes, levels, categories and sessions).
        '''
        classDescription = getattr(event, 'classDescription', None)
        category = getattr(event, 'category', None)

        if self.classvoucher_set.exists() and not self.classvoucher_set.filter(
            classDescription=classDescription
        ).exists():
            return False
        if self.dancetypevoucher_set.exists() and not self.dancetypevoucher_set.filter(
            danceTypeLevel=getattr(classDescription, 'danceTypeLevel', None)
        ).exists():
            return False

        # Series and public events have different types of category, so an
        # event of the other type never has a category that qualifies.
        if self.seriescategoryvoucher_set.exists() and (
            not isinstance(category, SeriesCategory) or
            not self.seriescategoryvoucher_set.filter(seriesCategory=category).exists()
        ):
            return False
        if self.publiceventcategoryvoucher_set.exists() and (
            not isinstance(category, PublicEventCategory) or
            not self.publiceventcategoryvoucher_set.filter(
                publicEventCategory=category
            ).exists()
        ):
            return False

        if self.sessionvoucher_set.exists() and not self.sessionvoucher_set.filter(
            session=getattr(event, 'session', None)
        ).exists():
            return False
        return True

    @property
    def isAttendeeRestricted(self):
        '''
        Is this voucher only for first-time customers, or only for previous
        customers?  These conditions apply to the person that each registration
        is for, while restrictions to specific customers or customer groups
        apply to the person who is paying.
        '''
        return self.forFirstTimeCustomersOnly or self.forPreviousCustomersOnly

    def customerQualifies(self, customer):
        '''
        Does the passed customer meet this voucher's conditions on first-time
        or previous customers?  No customer (e.g. a person who has never
        registered before) is a first-time customer.
        '''
        registered = customer.numEventRegistrations if customer else 0
        if self.forFirstTimeCustomersOnly and registered > 0:
            return False
        if self.forPreviousCustomersOnly and registered == 0:
            return False
        return True

    def eligibleItemIds(self, invoiceItems, attendee=NOT_GIVEN, checkAttendees=True):
        '''
        Return the set of the ids (as strings) of the passed invoice items that
        this voucher can be used for.

        A voucher with no restrictions on classes, events, or first-time or
        previous customers can be used for every item.  Otherwise, it can be
        used for registrations for the events that qualify, by people who
        qualify.  Events that are included with another event (e.g. as part of
        a pass) follow that event.  A voucher that can be used for the entire
        invoice can be used for every item if at least one registration
        qualifies.

        The person that each registration is for is the customer recorded for
        it, unless an attendee is passed, in which case that customer (or None,
        for someone who has never registered) is used for every registration.
        If checkAttendees is False, then the people are not checked at all
        (e.g. before it is known who each registration is for).
        '''
        items = list(invoiceItems)
        checkAttendees = checkAttendees and self.isAttendeeRestricted
        if not self.isEventRestricted and not self.isAttendeeRestricted:
            return {str(x.id) for x in items}

        # Cache the result for each event and customer, since a pass and the
        # events that it includes are checked together.
        event_results = {}
        customer_results = {}

        def itemQualifies(item):
            if item.parent_item_id:
                return itemQualifies(item.parent_item)
            try:
                eventRegistration = item.eventRegistration
            except ObjectDoesNotExist:
                return False

            if self.isEventRestricted:
                event = eventRegistration.event
                if event.id not in event_results:
                    event_results[event.id] = self.eventQualifies(event)
                if not event_results[event.id]:
                    return False

            if checkAttendees:
                customer = (
                    eventRegistration.customer if attendee is NOT_GIVEN
                    else attendee
                )
                key = getattr(customer, 'id', None)
                if key not in customer_results:
                    customer_results[key] = self.customerQualifies(customer)
                if not customer_results[key]:
                    return False
            return True

        qualifying = {str(x.id) for x in items if itemQualifies(x)}
        if qualifying and self.appliesToEntireInvoice:
            return {str(x.id) for x in items}
        return qualifying

    def validate(
        self, customer=None, events=None, payAtDoor=False, raise_errors=True,
        return_amount=False, validate_customer=True, validate_events=True,
        invoiceItems=None, attendee=NOT_GIVEN, checkAttendees=True
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

        The customer is the person who is paying.  If the invoice items are
        passed, then the voucher must be usable for at least one of them (see
        eligibleItemIds(), which also takes the attendee and checkAttendees
        arguments), and the conditions on first-time and previous customers
        are checked for the person that each registration is for, not for the
        person who is paying.  Without invoice items (e.g. before checkout),
        the events and the person who is paying are checked.
        '''

        errors = []
        warnings = []

        if events is None:
            events = Event.objects.none()

        if not hasattr(events, '__iter__'):
            raise ValueError(_('Invalid event list.'))
        if (type(customer) not in [Customer, type(None)]):
            raise ValueError(_('Invalid customer.'))

        # Assume that a non-queryset is a list of IDs.
        if (
            (not isinstance(events, QuerySet)) or
            issubclass(getattr(events, '_iterable_class', int), FlatValuesListIterable)
        ):
            events = Event.objects.filter(id__in=events)

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

        event_restricted = self.isEventRestricted
        if invoiceItems is not None:
            invoiceItems = list(invoiceItems)

        first_time_error = ValidationError(
            _('This voucher can only be used by first time customers.'),
            code='not_first_time_customer'
        )
        previous_customer_error = ValidationError(
            _(
                'This voucher can only be used by existing customers.' +
                '  If you are an existing customer, be sure to register' +
                ' with the same email address that you have used previously.'
            ),
            code='not_existing_customer',
        )

        # Only validate events contents if specified (default is True)
        if validate_events:
            # A voucher that is restricted to specific classes or events can
            # only be used when at least one registration for them is being
            # made (so not, for example, for merchandise alone).  It is then
            # only used for the items that qualify for it, unless it can be
            # used for the entire invoice (see eligibleItemIds()).
            if invoiceItems is not None:
                events_qualify = bool(
                    self.eligibleItemIds(invoiceItems, checkAttendees=False)
                )
            else:
                events_qualify = (
                    not event_restricted or
                    any(self.eventQualifies(x) for x in events)
                )

            if not events_qualify:
                errors.append(
                    ValidationError(
                        _('This voucher can be only used for specific classes or events.'),
                        code='no_eligible_events'
                    )
                )
            elif (
                invoiceItems is not None and checkAttendees and
                self.isAttendeeRestricted and
                not self.eligibleItemIds(invoiceItems, attendee=attendee)
            ):
                # No registration is for a person who meets the conditions on
                # first-time or previous customers.
                errors.append(
                    first_time_error if self.forFirstTimeCustomersOnly
                    else previous_customer_error
                )
        elif event_restricted:
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
                elif cgvs.exists() and (
                    not customer or
                    not cgvs.filter(group__in=customer.groups.all()).exists()
                ):
                    errors.append(
                        ValidationError(
                            _('This voucher is associated with a specific customer group.'),
                            code='customergroup_invalid'
                        )
                    )

            # Without invoice items, the conditions on first-time and previous
            # customers are checked for the person who is paying.  Otherwise,
            # they were checked above for each registration.
            if invoiceItems is None and not self.customerQualifies(customer):
                errors.append(
                    first_time_error if (
                        self.forFirstTimeCustomersOnly and
                        customer and customer.numEventRegistrations > 0
                    ) else previous_customer_error
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

    def clean(self):
        '''
        A code that is also the code of a discount belongs to the discount, so
        a voucher with that code could never be used.
        '''
        super().clean()
        if self.voucherId and apps.is_installed('danceschool.discounts'):
            DiscountCombo = apps.get_model('discounts', 'DiscountCombo')
            if DiscountCombo.objects.filter(voucherId=self.voucherId).exists():
                raise ValidationError({'voucherId': _(
                    'This code is already the code of a discount.'
                )})

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
