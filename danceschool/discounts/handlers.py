from django.core.exceptions import ValidationError
from django.dispatch import receiver
from django.db.models import Q, Value, CharField, F, Case, When
from django.db.models.query import QuerySet
from django.apps import apps
from django.utils import timezone

import logging
from collections import OrderedDict

from danceschool.core.signals import (
    request_discounts, check_student_info, apply_discount, apply_addons,
    post_registration, get_eventregistration_data
)
from danceschool.core.constants import getConstant, REG_VALIDATION_STR
from danceschool.core.models import Customer, EventRegistration, Registration

from .helpers import prepareCartObjects, getApplicableDiscountCombos
from .models import DiscountCombo, RegistrationDiscount


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(request_discounts)
def getBestDiscount(sender, **kwargs):
    '''
    When a customer registers for events, discounts may need to be automatically
    applied.  A given shopping cart may, in fact, be eligible for multiple
    different types of discounts (e.g. hours-based discounts for increasing
    numbers of class hours), but typically, only one discount should be applied.
    Therefore, this handler loops through all potential discounts, finds the
    ones that are applicable to the passed registration or set of items, and
    returns the code and discounted price of the best available discount, in a
    tuple of the form (code, discounted_price).
    '''
    if not getConstant('general__discountsEnabled'):
        return

    logger.debug('Signal fired to request discounts.')

    voucher_code = kwargs.get('voucher_code', None)
    reg = kwargs.pop('registration', None)
    invoice = kwargs.get('invoice', None)
    cart_items = kwargs.get('cart_items', [])
    customer_final = kwargs.pop('customer_final', False)

    # Use payAtDoor from the Registration when available; fall back to the
    # value passed explicitly by the caller (e.g. CartView preview).
    payAtDoor = getattr(reg, 'payAtDoor', None)
    if payAtDoor is None:
        payAtDoor = kwargs.get('payAtDoor', False)

    cart_kwargs = prepareCartObjects(reg, invoice, cart_items, payAtDoor=payAtDoor)
    eligible_list = cart_kwargs.get('cart_object_list')
    # Check if this is a new customer, who may be eligible for special discounts
    newCustomer = True
    customer = Customer.objects.filter(
        email=invoice.email,
        first_name=invoice.firstName,
        last_name=invoice.lastName
    ).first()
    if (customer and customer.numEventRegistrations > 0) or not customer_final:
        newCustomer = False

    # student=True if the signal caller explicitly flagged it (e.g. CartView
    # discount preview) OR if any EventRegistration on this reg has student=True.
    student = kwargs.get('student', False) or cart_kwargs.get('student', False)

    # Get the applicable discounts and sort them in ascending category order
    # so that the best discounts are always listed in the order that they will
    # be applied.
    discountCodesApplicable = getApplicableDiscountCombos(
        cart_object_list=eligible_list,
        customer=customer, newCustomer=newCustomer,
        student=student,
        dateTime=getattr(reg, 'dateTime', timezone.now()),
        payAtDoor=payAtDoor,
        voucher_code=voucher_code, addOn=False, cannotCombine=False,
    )
    discountCodesApplicable.sort(key=lambda x: x.code.category.order)

    # Once we have a list of codes to try, calculate the discounted price for
    # each possibility, and pick the one in each category that has the lowest
    # total price.  We also need to keep track of the way in which some
    # discounts are allocated across individual events.
    best_discounts = OrderedDict()

    initial_prices = [x['base_price'] for x in eligible_list]
    initial_total = sum(initial_prices)

    if discountCodesApplicable:
        net_allocated_prices = initial_prices
        net_precategory_price = initial_total
        last_category = discountCodesApplicable[0].code.category

    for discount in discountCodesApplicable:

        # If the category has changed, then the new net_allocated_prices and the
        # new net_precategory price are whatever was found to be best in the
        # last category.
        if (discount.code.category != last_category):
            last_category = discount.code.category

            if best_discounts:
                # Since this is an OrderedDict, we can get the last element of
                # the dict from the iterator, which is the last category for
                # which there was a valid discount.
                last_discount = best_discounts.get(next(reversed(best_discounts)))
                net_allocated_prices = last_discount.net_allocated_prices
                net_precategory_price = last_discount.net_price

        # The second item in each tuple is now adjusted, so that each item that
        # is wholly or partially applied against the discount will be wholly
        # (value goes to 0) or partially subtracted from the remaining value
        # to be calculated at full price.
        tieredTuples = [(x, 1) for x in eligible_list[:]]

        for itemTuple in discount.itemTuples:
            tieredTuples = [
                (p, q) if p != itemTuple[0] else
                (p, q - itemTuple[1]) for (p, q) in tieredTuples
            ]

        response = discount.code.applyAndAllocate(
            net_allocated_prices, tieredTuples, payAtDoor
        )

        # Once the final price has been calculated, apply it iff it is less than
        # the previously best discount found.
        current_code = best_discounts.get(discount.code.category.name, None)
        if (
            response and (
                (not current_code and response.net_price < net_precategory_price) or
                (current_code and response.net_price < current_code.net_price)
            )
        ):
            best_discounts[discount.code.category.name] = response

    # Now, repeat the basic process for codes that cannot be combined.  These
    # codes are always compared against the base price, and there is no need to
    # allocate across items since only one code will potentially be applied.
    uncombinedCodesApplicable = getApplicableDiscountCombos(
        cart_object_list=cart_kwargs.get('cart_object_list'),
        customer=customer, newCustomer=newCustomer,
        student=student,
        dateTime=getattr(reg, 'dateTime', timezone.now()),
        payAtDoor=payAtDoor,
        voucher_code=voucher_code, addOn=False, cannotCombine=True,
    )

    for discount in uncombinedCodesApplicable:

        # The second item in each tuple is now adjusted, so that each item that
        # is wholly or partially applied against the discount will be wholly
        # (value goes to 0) or partially subtracted from the remaining value to
        # be calculated at full price.
        tieredTuples = [(x, 1) for x in eligible_list[:]]

        for itemTuple in discount.itemTuples:
            tieredTuples = [
                (p, q) if p != itemTuple[0] else (p, q - itemTuple[1])
                for (p, q) in tieredTuples
            ]

        response = discount.code.applyAndAllocate(
            initial_prices, tieredTuples, payAtDoor
        )

        # Once the final price has been calculated, apply it iff it is less than
        # the previously best discount or combination of discounts found.
        if (
            response and
            response.net_price < min(
                [x.net_price for x in best_discounts.values()] + [initial_total]
            )
        ):
            best_discounts = OrderedDict({discount.code.category.name: response})

    if not best_discounts:
        logger.debug('No applicable discounts found.')

    # Return the list of discounts to be applied (in DiscountInfo tuples), along
    # with the additional price of ineligible items to be added.
    return DiscountCombo.DiscountApplication(
        [x for x in best_discounts.values()], cart_kwargs.get('ineligible_total')
    )


@receiver(check_student_info)
def checkVoucherFieldForDiscount(sender, **kwargs):
    '''
    If the given voucher code applies to a discount, then ensure that the
    discount actually applies.
    '''
    logger.debug('Signal to check RegistrationContactForm handled by discounts app.')

    formData = kwargs.get('data', {})
    customer_final = kwargs.pop('customer_final', False)

    id = formData.get('gift', '')
    first = formData.get('firstName')
    last = formData.get('lastName')
    email = formData.get('email')

    if id == '':
        return

    objs = DiscountCombo.objects.filter(voucherId=id)
    if not objs.exists():
        return
    else:

        registration = kwargs.get('registration', None)
        if not registration:
            invoice = kwargs.get('invoice', None)
            registration = Registration.objects.filter(invoice=invoice).first()
        if not registration:
            return
        cart_kwargs = prepareCartObjects(registration, kwargs.get('invoice', None))

        newCustomer = True
        customer = Customer.objects.filter(
            first_name=first,
            last_name=last,
            email=email).first()
        if (customer and customer.numEventRegistrations > 0) or not customer_final:
            newCustomer = False

        # This will raise any other errors that may be relevant
        errors_found = []
        for obj in objs:
            try:
                obj.validateForCart(
                    cart_object_list=cart_kwargs.get('cart_object_list'),
                    newCustomer=newCustomer,
                    student=cart_kwargs.get('student', False),
                    customer=customer,
                    dateTime=registration.dateTime,
                    payAtDoor=registration.payAtDoor
                )
            except ValidationError as e:
                errors_found.append(e)
            else:
                # A discount successfully validated, so no need to check others
                errors_found = []
                break
        if errors_found:
            # Ensures that the error is applied to the correct field. In case of
            # multiple discounts with the same ID, we will report the error
            # message associated with the first one.
            raise ValidationError({'gift': errors_found[0]})
            
    # If we got this far, then the discount is determined to be valid, so the
    # registration can proceed with no errors.
    return


@receiver(apply_discount)
def applyTemporaryDiscount(sender, **kwargs):
    # Get the registration and the customer
    if not getConstant('general__discountsEnabled'):
        return

    logger.debug('Signal fired to apply discounts.')

    reg = kwargs.pop('registration', None)
    if not reg:
        invoice = kwargs.get('invoice', None)
        reg = Registration.objects.filter(invoice=invoice).first()

    discount = kwargs.pop('discount', None)
    discountAmount = kwargs.pop('discount_amount', None)

    if not reg or not discount:
        logger.warning('Incomplete information passed, discounts not applied.')
        return

    obj = RegistrationDiscount.objects.update_or_create(
        registration=reg,
        discount=discount,
        defaults={'discountAmount': discountAmount, 'applied': False},
    )[0]
    logger.debug('Temporary discount record created.')
    return obj


@receiver(apply_addons)
def getAddonItems(sender, **kwargs):
    # Check if this is a new customer
    if not getConstant('general__discountsEnabled'):
        return

    logger.debug('Signal fired to request free add-ons.')

    reg = kwargs.pop('registration', None)
    invoice = kwargs.get('invoice', None)
    customer_final = kwargs.pop('customer_final', False)

    if not reg:
        reg = Registration.objects.filter(invoice=invoice).first()

    if not reg or not invoice:
        logger.warning('No registration passed, addons not applied.')
        return

    newCustomer = True
    customer = Customer.objects.filter(
        email=invoice.email, first_name=invoice.firstName, last_name=invoice.lastName
    ).first()
    if (customer and customer.numEventRegistrations > 0) or not customer_final:
        newCustomer = False

    cart_object_list = prepareCartObjects(reg=reg).get('cart_object_list', [])

    # TODO: Fix student status
    student = False

    availableAddons = getApplicableDiscountCombos(
        cart_object_list, newCustomer, student,
        customer=customer, addOn=True, dateTime=reg.dateTime,
        payAtDoor=reg.payAtDoor
    )
    return [x.code.name for x in availableAddons]


@receiver(post_registration)
def applyFinalDiscount(sender, **kwargs):
    # Get the registration and the customer
    if not getConstant('general__discountsEnabled'):
        return

    logger.debug('Signal fired to finalize application of discounts.')

    reg = kwargs.pop('registration', None)
    if not reg:
        invoice = kwargs.get('invoice', None)
        reg = Registration.objects.filter(invoice=invoice).first()

    if not reg:
        logger.debug('No registration passed, discounts not applied.')
        return

    trds = RegistrationDiscount.objects.filter(registration=reg)
    for temp_discount in trds:
        temp_discount.applied = True
        temp_discount.save()

    logger.debug('Discounts applied.')
    return trds


@receiver(get_eventregistration_data)
def reportDiscounts(sender, **kwargs):
    if not getConstant('general__discountsEnabled'):
        return

    logger.debug('Signal fired to return discounts associated with registrations')

    reg_ids = kwargs.pop('eventregistrations', [])

    discount_data = RegistrationDiscount.objects.filter(
        registration__eventregistration__id__in=reg_ids,
    ).annotate(
        name=F('discount__name'),
        type=Value('discount', output_field=CharField()),
        amount=F('discountAmount'),
        reg_id=F('registration__eventregistration__id'),
    ).values('id', 'amount', 'name', 'type', 'reg_id')

    extras = {}
    for row in discount_data:
        extras.setdefault(row['reg_id'], []).append(
            {k: v for k, v in row.items() if k != 'reg_id'}
        )

    return extras
