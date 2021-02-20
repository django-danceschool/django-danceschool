from django.dispatch import receiver
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from django.db.models import Value, CharField
from django.db.models.query import QuerySet
from django.db.models.functions import Concat

from danceschool.core.signals import (
    post_student_info, apply_price_adjustments, get_customer_data,
    check_student_info, get_eventregistration_data, check_voucher,
    invoice_finalized
)
from danceschool.core.models import (
    Customer, EventRegistration, Event, Registration
)
from danceschool.core.constants import getConstant, REG_VALIDATION_STR

import logging

from .models import Voucher, VoucherUse
from .helpers import awardReferrers, ensureReferralVouchersExist


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(check_student_info)
def checkVoucherField(sender, **kwargs):
    '''
    Check that the given voucher code is valid
    '''
    logger.debug('Signal to check RegistrationContactForm handled by vouchers app.')

    formData = kwargs.get('formData', {})
    request = kwargs.get('request', {})
    invoice = kwargs.get('invoice', None)
    registration = kwargs.get('registration', None)
    session = getattr(request, 'session', {}).get(REG_VALIDATION_STR, {})

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

    if not registration:
        registration = Registration.objects.filter(invoice=invoice).first()
    events = Event.objects.none()

    if registration:
        events = Event.objects.filter(
            eventregistration__registration=registration
        ).exclude(eventregistration__dropIn=True).values_list('id', flat=True)

    obj = Voucher.objects.filter(voucherId=id).first()
    if not obj:
        raise ValidationError({'gift': _('Invalid Voucher Id')})
    else:
        customer = Customer.objects.filter(
            first_name=first,
            last_name=last,
            email=email).first()

        # This will raise any other errors that may be relevant
        try:
            obj.validate(
                payAtDoor=getattr(registration, 'payAtDoor', False),
                customer=customer,
                events=events
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
    voucherId = kwargs.get('voucherId', None)
    customer = kwargs.get('customer', None)
    validate_customer = kwargs.get('validateCustomer', False)

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
    if not registration:
        registration = Registration.objects.filter(invoice=invoice).first()
    events = Event.objects.none()

    if registration:
        events = Event.objects.filter(
            eventregistration__registration=registration
        ).exclude(eventregistration__dropIn=True).values_list('id', flat=True)

    return obj.validate(
        customer=customer, events=events,
        payAtDoor=getattr(registration, 'payAtDoor', False),
        raise_errors=False, return_amount=True,
        validate_customer=validate_customer
    )


@receiver(post_student_info)
def applyVoucherCodeTemporarily(sender, **kwargs):
    '''
    When the core registration system creates a temporary registration with a voucher code,
    the voucher app looks for vouchers that match that code and creates VoucherUse
    objects to keep track of the fact that the voucher may be used.
    '''
    logger.debug('Signal fired to apply vouchers preliminarily.')

    invoice = kwargs.pop('invoice')
    voucherId = invoice.data.get('gift', '')

    try:
        voucher = Voucher.objects.get(voucherId=voucherId)
    except ObjectDoesNotExist:
        logger.debug('No applicable vouchers found.')
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

    # Put referral vouchers first, so that they are applied last in the loop.
    referral_cat = getConstant('referrals__referrerCategory')

    tvus = list(invoice.voucheruse_set.filter(
        voucher__category=referral_cat,
        applied=False
    ).order_by('-beforeTax')) + list(invoice.voucheruse_set.exclude(
        voucher__category=referral_cat,
        applied=False
    ).order_by('-beforeTax'))

    response = {
        'total_pretax': 0,
        'total_posttax': 0,
        'items': [],
    }

    if not tvus:
        logger.debug('No applicable vouchers found.')
        return response

    remaining_pretax = invoice.total + prior_adjustment
    remaining_posttax = (
        invoice.total + prior_adjustment +
        invoice.taxes + invoice.adjustments
    )

    while (remaining_pretax > 0 or remaining_posttax > 0) and tvus:
        tvu = tvus.pop()

        if tvu.voucher.maxAmountPerUse:
            amount = min(tvu.voucher.amountLeft, tvu.voucher.maxAmountPerUse)
        else:
            amount = tvu.voucher.amountLeft

        # The amount of the voucher that can be used depends on wh
        if tvu.beforeTax:
            amount = min(remaining_pretax, amount)
            remaining_pretax -= amount
            response['total_pretax'] += amount
        else:
            amount = min(remaining_posttax, amount)
            response['total_posttax'] += amount

        remaining_posttax -= amount
        tvu.amount = amount
        tvu.save()
        response['items'].append({
            'name': tvu.voucher.name,
            'amount': amount,
            'beforeTax': tvu.beforeTax,
        })

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


@receiver(get_customer_data)
def provideCustomerReferralCode(sender, **kwargs):
    '''
    If the vouchers app is installed and referrals are enabled,
    then the customer's profile page can show their voucher referral code.
    '''
    customer = kwargs.pop('customer')
    if getConstant('vouchers__enableVouchers') and getConstant('referrals__enableReferralProgram'):
        vrd = ensureReferralVouchersExist(customer)

        return {
            'referralVoucherId': vrd.referreeVoucher.voucherId
        }


@receiver(get_eventregistration_data)
def reportVouchers(sender, **kwargs):
    if not getConstant('vouchers__enableVouchers'):
        return

    logger.debug('Signal fired to return vouchers associated with registrations')

    regs = kwargs.pop('eventregistrations', None)
    if not regs or not isinstance(regs, QuerySet) or not (regs.model == EventRegistration):
        logger.warning('No/invalid EventRegistration queryset passed, so vouchers not found.')
        return

    extras = {}
    regs = regs.filter(registration__invoice__voucheruse__isnull=False).prefetch_related(
        'registration__invoice__voucheruse_set', 'registration__invoice__voucheruse_set__voucher'
    )

    for reg in regs:
        extras[reg.id] = list(reg.registration.invoice.voucheruse_set.annotate(
            name=Concat('voucher__voucherId', Value(': '), 'voucher__name', output_field=CharField()),
            type=Value('voucher', output_field=CharField()),
        ).values('id', 'amount', 'name', 'type'))

    return extras
