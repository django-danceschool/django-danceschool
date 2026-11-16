from django.apps import apps
from django.dispatch import receiver
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from django.db.models import Value, CharField, F
from django.db.models.query import QuerySet
from django.db.models.functions import Concat

import logging
from importlib import import_module

from danceschool.core.signals import (
    post_student_info, apply_price_adjustments, get_person_data,
    check_student_info, get_eventregistration_data, check_voucher,
    invoice_finalized
)
from danceschool.core.models import (
    Customer, EventRegistration, Event, Registration
)
from danceschool.core.constants import getConstant, REG_VALIDATION_STR

from .models import Voucher, VoucherUse
from .helpers import awardReferrers, ensureReferralVouchersExist


# Define logger for this file
logger = logging.getLogger(__name__)


def registrationEvents(registration):
    '''
    Return the events that the passed Registration is for, which are the
    events that a voucher restricted to specific classes or events may
    qualify for.  Events that are included with another event (e.g. as part
    of a pass) are left out, because they qualify for a voucher only if the
    event that they are included with does (see Voucher.eligibleItemIds()).
    '''
    if not registration:
        return Event.objects.none()
    return Event.objects.filter(
        id__in=registration.eventregistration_set.filter(
            invoiceItem__parent_item__isnull=True
        ).values_list('event_id', flat=True)
    )


def cartEvents(cart_items):
    ''' Return the events in a cart that has not been checked out. '''
    return Event.objects.filter(
        id__in=[x.get('item_id') for x in cart_items if x.get('item_type') == 'Event']
    )


def currentValue(item, field):
    '''
    The value of a field of an invoice item, as most recently calculated. The
    invoice items passed with some signals come from Invoice.updateTotals(),
    which annotates the results of an allocation that has not been saved
    (e.g. newTotal), and those values are used when they are present.
    '''
    value = getattr(item, 'new' + field[0].upper() + field[1:], None)
    if value is None:
        value = getattr(item, field, 0)
    return value or 0


@receiver(check_student_info)
def checkVoucherField(sender, **kwargs):
    '''
    Check that the given voucher code is valid
    '''
    logger.debug('Signal to check RegistrationContactForm handled by vouchers app.')

    formData = kwargs.get('data', {})
    request = kwargs.get('request', {})
    invoice = kwargs.get('invoice', None)
    registration = kwargs.get('registration', None)
    session = getattr(request, 'session', {}).get(REG_VALIDATION_STR, {})
    cart_items = session.get('cart', {}).get('items', [])

    id = formData.get('gift', '')
    first = formData.get('firstName')
    last = formData.get('lastName')
    email = formData.get('email')

    # Clean out the session data relating to vouchers so that we can revalidate it.
    session.pop('total_voucher_amount', 0)
    session.pop('voucher_names', None)
    session.pop('gift', None)

    if id == '':
        return

    if not getConstant('vouchers__enableVouchers'):
        raise ValidationError({'gift': _('Vouchers are disabled.')})

    if session.get('gift', '') != '':
        raise ValidationError({'gift': _('Can\'t have more than one voucher')})

    if invoice and (not registration):
        registration = Registration.objects.filter(invoice=invoice).first()

    if registration:
        events = registrationEvents(registration)
    else:
        events = cartEvents(cart_items)

    # If a discount code with this ID exists, then no further validation can be
    # performed here. Otherwise, ensure that a voucher ID exists matching this
    # code.
    if apps.is_installed('danceschool.discounts'):
        discount_models = import_module('danceschool.discounts.models')
        discount_obj = discount_models.DiscountCombo.objects.filter(voucherId=id).first()
        if discount_obj:
            return

    obj = Voucher.objects.filter(voucherId=id).first()
    if not obj:
        raise ValidationError({'gift': _('Invalid Voucher Id')})
    else:
        customer = Customer.objects.filter(
            first_name=first,
            last_name=last,
            email=email).first()

        # If the invoice exists, then the voucher must be usable for at least
        # one of its items.  If the name of the person that each registration
        # is for is asked for next, then those people are checked once their
        # names are known (in applyVoucherCodeTemporarily()).  Otherwise, the
        # person entering this form is the person that every registration is
        # for, even if a different person was recorded on an earlier attempt.
        if not invoice and registration:
            invoice = registration.invoice
        invoiceItems = invoice.invoiceitem_set.all() if invoice else None
        multiReg = getattr(kwargs.get('instance', None), '_multireg', False)

        # This will raise any other errors that may be relevant
        try:
            obj.validate(
                payAtDoor=getattr(registration, 'payAtDoor', False),
                customer=customer,
                events=events,
                invoiceItems=invoiceItems,
                attendee=customer,
                checkAttendees=not multiReg,
            )
        except ValidationError as e:
            # Ensures that the error is applied to the correct field
            raise ValidationError({'gift': e})

    # If we got this far, then the voucher is determined to be valid, so the registration
    # can proceed with no errors.
    return


@receiver(check_voucher)
def checkVoucherCode(sender, **kwargs):
    '''
    Check that the given voucher code is valid.
    '''
    logger.debug('Signal to check voucher code handled by vouchers app.')

    invoice = kwargs.get('invoice', None)
    registration = kwargs.get('registration', None)
    cart_items = kwargs.get('cart_items', [])
    voucherId = kwargs.get('voucherId', None)
    customer = kwargs.get('customer', None)
    validate_customer = kwargs.get('validateCustomer', False)
    pay_at_door = kwargs.get('payAtDoor', None)

    errors = []

    if not voucherId:
        errors.append({
            'code': 'no_code',
            'message': _('No voucher code has been specified.')
        })

    if not getConstant('vouchers__enableVouchers'):
        errors.append({
            'code': 'disabled',
            'message': _('Vouchers are disabled.')
        })

    obj = Voucher.objects.filter(voucherId=voucherId).first()
    if not obj:
        errors.append({
            'code': 'invalid_id',
            'message': _('Invalid voucher Id')
        })

    if not obj or errors:
        return {
            'status': 'invalid',
            'errors': errors,
        }

    # If we got this far, then we can just use the model-level validation. The
    # dictionary that it returns takes the same form as the one that is returned
    # above if an error has already been found.
    if invoice and (not registration):
        registration = Registration.objects.filter(invoice=invoice).first()

    if registration:
        events = registrationEvents(registration)
    else:
        events = cartEvents(cart_items)

    # Use the explicitly-passed payAtDoor when available (e.g. cart preview);
    # fall back to the registration's attribute when we have one.
    if pay_at_door is None:
        pay_at_door = getattr(registration, 'payAtDoor', False)

    # If there is no cart yet (e.g. a voucher code passed in a link to the
    # registration page), then the events cannot be checked yet.  They are
    # checked once there is a cart or a registration.
    if not invoice and registration:
        invoice = registration.invoice

    # The invoice items, with their prices after any discounts if they were
    # passed.  The people that the registrations are for are only checked if
    # the customer is to be checked.
    items = None
    if invoice:
        items = kwargs.get('items')
        if items is None:
            items = invoice.invoiceitem_set.all()
        items = list(items)

    result = obj.validate(
        customer=customer, events=events,
        payAtDoor=pay_at_door,
        raise_errors=False, return_amount=True,
        validate_customer=validate_customer,
        validate_events=bool(registration or cart_items),
        invoiceItems=items, checkAttendees=validate_customer,
    )

    # A voucher that is restricted to specific classes or events, or to
    # first-time or previous customers, can only be used for the items that
    # qualify for it, so the amount that can be used is limited to the price
    # of those items: before tax (eligible_total), and after tax
    # (eligible_total_posttax), for vouchers applied after tax.  Both are None
    # when there is no limit other than the price of the cart.
    result['eligible_total'] = None
    result['eligible_total_posttax'] = None

    # A voucher that depends on who is paying (a specific customer or customer
    # group), or on who each registration is for (first-time or previous
    # customers), is pending until that is known, so that the amount shown
    # for it may still change.
    attendees_known = False
    if items is not None and validate_customer:
        eventRegistrations = []
        for x in items:
            if x.parent_item_id:
                continue
            try:
                eventRegistrations.append(x.eventRegistration)
            except ObjectDoesNotExist:
                continue
        attendees_known = all([er.customer_id for er in eventRegistrations])
    result['customer_pending'] = bool(
        (not obj.isValidForAnyCustomer and not validate_customer) or
        (obj.isAttendeeRestricted and not attendees_known)
    )

    if result.get('status') != 'valid':
        return result

    if items is not None and (
        obj.isEventRestricted or (obj.isAttendeeRestricted and validate_customer)
    ):
        eligible = obj.eligibleItemIds(items, checkAttendees=validate_customer)
        if len(eligible) < len(items):
            buyer_pays = invoice.buyerPaysSalesTax
            eligible_items = [x for x in items if str(x.id) in eligible]
            result['eligible_total'] = sum(
                [currentValue(x, 'total') for x in eligible_items]
            )
            result['eligible_total_posttax'] = sum([
                currentValue(x, 'total') + currentValue(x, 'adjustments') +
                (currentValue(x, 'taxes') if buyer_pays else 0)
                for x in eligible_items
            ])
    elif items is None and cart_items and obj.isEventRestricted and (
        not obj.appliesToEntireInvoice
    ):
        # Before checkout there are no invoice items, so the prices of the
        # events in the cart are used.  (Who each registration is for is not
        # known yet, so that is not checked here.)
        events_by_id = {x.id: x for x in events}
        eligible_total = 0
        for cart_item in cart_items:
            event = events_by_id.get(cart_item.get('item_id'))
            if cart_item.get('item_type') == 'Event' and event and obj.eventQualifies(event):
                eligible_total += (
                    event.getBasePrice(payAtDoor=pay_at_door) *
                    (cart_item.get('quantity') or 1)
                )
        result['eligible_total'] = eligible_total
        result['eligible_total_posttax'] = eligible_total
    return result


@receiver(post_student_info)
def applyVoucherCodeTemporarily(sender, **kwargs):
    '''
    When the core registration system creates a temporary registration with a voucher code,
    the voucher app looks for vouchers that match that code and creates VoucherUse
    objects to keep track of the fact that the voucher may be used.
    '''
    logger.debug('Signal fired to apply vouchers preliminarily.')

    invoice = kwargs.pop('invoice')
    voucherId = invoice.data.get('discount_code') or invoice.data.get('gift', '')

    # This signal is sent again if the customer goes back and submits their
    # information again (possibly with a different voucher code, or with none),
    # so any use of a voucher code that was recorded previously and has not
    # been finalized is removed first.  Referrer vouchers are handled
    # separately in applyReferrerVouchersTemporarily().
    prior_uses = invoice.voucheruse_set.filter(applied=False)
    referral_cat = getConstant('referrals__referrerCategory')
    if referral_cat:
        prior_uses = prior_uses.exclude(voucher__category=referral_cat)
    prior_uses.delete()

    try:
        voucher = Voucher.objects.get(voucherId=voucherId)
    except ObjectDoesNotExist:
        logger.debug('No applicable vouchers found.')
        return

    # The voucher code may not have been checked before this point (e.g. it
    # was passed with the cart, and it was not entered on the customer
    # information form), so all of the restrictions on the use of the voucher
    # are checked here before it is applied.
    registration = (
        kwargs.get('registration') or
        Registration.objects.filter(invoice=invoice).first()
    )
    events = registrationEvents(registration)

    customer = Customer.objects.filter(
        first_name=invoice.firstName, last_name=invoice.lastName,
        email=invoice.email
    ).first()

    # By this point, the person that each registration is for is known, and
    # the conditions on first-time and previous customers are checked for
    # each of them.
    result = voucher.validate(
        customer=customer, events=events,
        payAtDoor=getattr(registration, 'payAtDoor', False),
        raise_errors=False,
        invoiceItems=invoice.invoiceitem_set.all(),
    )
    if result.get('status') != 'valid':
        logger.debug(
            'Voucher %s cannot be used; skipping. %s', voucherId, result.get('errors')
        )
        return

    tvu = VoucherUse(
        voucher=voucher, invoice=invoice, beforeTax=voucher.beforeTax,
        amount=0, applied=False
    )
    tvu.save()
    logger.debug('Preliminary voucher use object created.')


@receiver(post_student_info)
def applyReferrerVouchersTemporarily(sender, **kwargs):
    '''
    Unlike voucher codes which have to be manually supplied, referrer discounts are
    automatically applied here, assuming that the referral program is enabled.
    '''

    # Only continue if the referral program is enabled
    if not getConstant('referrals__enableReferralProgram'):
        return

    logger.debug('Signal fired to temporarily apply referrer vouchers.')

    invoice = kwargs.pop('invoice')

    # Remove any use of referrer vouchers that was recorded previously and has
    # not been finalized, so that they are not applied more than once if this
    # signal is sent again.
    referral_cat = getConstant('referrals__referrerCategory')
    if referral_cat:
        invoice.voucheruse_set.filter(
            applied=False, voucher__category=referral_cat
        ).delete()

    # Email address is unique for users, so use that
    try:
        c = Customer.objects.get(user__email=invoice.email)
        vouchers = c.getReferralVouchers()
    except ObjectDoesNotExist:
        vouchers = None

    if not vouchers:
        logger.debug('No referral vouchers found.')
        return

    for v in vouchers:
        VoucherUse(
            voucher=v, invoice=invoice, beforeTax=v.beforeTax,
            amount=0, applied=False
        ).save()


@receiver(apply_price_adjustments)
def applyTemporaryVouchers(sender, **kwargs):
    invoice = kwargs.get('invoice')
    prior_adjustment = kwargs.get('prior_adjustment')

    logger.debug('Signal fired to apply preliminary vouchers.')

    referral_cat = getConstant('referrals__referrerCategory')
    unapplied = invoice.voucheruse_set.filter(applied=False)

    def inOrderOfUse(queryset):
        ''' Referral vouchers are used last. '''
        return (
            list(queryset.exclude(voucher__category=referral_cat)) +
            list(queryset.filter(voucher__category=referral_cat))
        )

    # Pre-tax vouchers are always used before post-tax vouchers, because they
    # reduce the tax, and so they reduce the amount that remains to be paid
    # with a post-tax voucher.
    pretax_uses = inOrderOfUse(unapplied.filter(beforeTax=True))
    posttax_uses = inOrderOfUse(unapplied.filter(beforeTax=False))

    # The amounts of the vouchers that are applied to each invoice item, before
    # and after tax, in the form {invoice item id: amount}.  The totals are
    # the sums of these.
    response = {
        'total_pretax': 0,
        'total_posttax': 0,
        'items': [],
        'item_pretax': {},
        'item_posttax': {},
    }

    if not pretax_uses and not posttax_uses:
        logger.debug('No applicable vouchers found.')
        return response

    # The invoice items, with their prices after any discounts.  If the caller
    # did not pass them, then the saved values are used.
    items = kwargs.get('items')
    if items is None:
        items = invoice.invoiceitem_set.all()
    items = list(items)

    def useVoucher(tvu, remaining):
        ''' Use as much of the voucher as is available and needed. '''
        amount = tvu.voucher.amountLeft
        if tvu.voucher.maxAmountPerUse:
            amount = min(amount, tvu.voucher.maxAmountPerUse)
        amount = max(min(remaining, amount), 0)

        tvu.amount = amount
        tvu.save()
        if amount > 0:
            response['items'].append({
                'name': tvu.voucher.name,
                'amount': amount,
                'beforeTax': tvu.beforeTax,
            })
        return amount

    def allocate(amount, ids, remaining, record):
        '''
        Take the amount of a voucher off of the eligible items, in proportion
        to what remains to be paid for each of them.
        '''
        available = sum([remaining[i] for i in ids])
        if amount <= 0 or available <= 0:
            return
        for i in ids:
            share = amount * (remaining[i] / available)
            remaining[i] -= share
            record[i] = record.get(i, 0) + share

    # The price that remains to be paid for each item, before tax.  A prior
    # adjustment (if one is passed) is taken off of every item in proportion
    # to its price.
    remaining_pretax = {str(x.id): max(currentValue(x, 'total'), 0) for x in items}
    initial_pretax = sum(remaining_pretax.values())
    if prior_adjustment and initial_pretax > 0:
        factor = max(initial_pretax + prior_adjustment, 0) / initial_pretax
        remaining_pretax = {k: v * factor for k, v in remaining_pretax.items()}

    for tvu in pretax_uses:
        ids = tvu.voucher.eligibleItemIds(items)
        amount = useVoucher(tvu, sum([remaining_pretax[i] for i in ids]))
        allocate(amount, ids, remaining_pretax, response['item_pretax'])
        response['total_pretax'] += amount

    # The amount that remains to be paid for each item, after tax.  Tax is
    # calculated on what remains of the price of each item, at that item's
    # own rate.  If the buyer does not pay sales tax, then the price already
    # includes the tax, so it is not added.
    remaining_posttax = {}
    for x in items:
        price = remaining_pretax[str(x.id)]
        taxes = price * ((x.taxRate or 0) / 100) if invoice.buyerPaysSalesTax else 0
        remaining_posttax[str(x.id)] = max(
            price + taxes + currentValue(x, 'adjustments'), 0
        )

    for tvu in posttax_uses:
        ids = tvu.voucher.eligibleItemIds(items)
        amount = useVoucher(tvu, sum([remaining_posttax[i] for i in ids]))
        allocate(amount, ids, remaining_posttax, response['item_posttax'])
        response['total_posttax'] += amount

    return response


@receiver(invoice_finalized)
def applyVoucherCodesFinal(sender, **kwargs):
    '''
    Once an invoice is finalized, vouchers are used and referrers are awarded.
    '''
    logger.debug('Signal fired to mark voucher codes as applied.')

    invoice = kwargs.pop('invoice')
    tvus = VoucherUse.objects.filter(invoice=invoice, applied=False)

    for vu in tvus:
        vu.applied = True
        vu.save()
        if getConstant('referrals__enableReferralProgram'):
            awardReferrers(vu)


@receiver(get_person_data)
def provideCustomerReferralCode(sender, **kwargs):
    '''
    If the vouchers app is installed and referrals are enabled,
    then the customer's profile page can show their voucher referral code.
    '''
    customer = kwargs.pop('customer', None)
    if (
        customer and getConstant('vouchers__enableVouchers') and
        getConstant('referrals__enableReferralProgram')
    ):
        vrd = ensureReferralVouchersExist(customer)

        return {'referralVoucherId': vrd.referreeVoucher.voucherId}


@receiver(get_eventregistration_data)
def reportVouchers(sender, **kwargs):
    if not getConstant('vouchers__enableVouchers'):
        return

    logger.debug('Signal fired to return vouchers associated with registrations')

    reg_ids = kwargs.pop('eventregistrations', [])

    voucher_data = VoucherUse.objects.filter(
        invoice__registration__eventregistration__id__in=reg_ids,
    ).annotate(
        name=Concat(
            'voucher__voucherId', Value(': '), 'voucher__name',
            output_field=CharField()
        ),
        type=Value('voucher', output_field=CharField()),
        reg_id=F('invoice__registration__eventregistration__id'),
    ).values('id', 'amount', 'name', 'type', 'reg_id')

    extras = {}
    for row in voucher_data:
        extras.setdefault(row['reg_id'], []).append(
            {k: v for k, v in row.items() if k != 'reg_id'}
        )

    return extras
