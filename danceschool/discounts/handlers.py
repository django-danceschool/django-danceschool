from django.dispatch import receiver
from django.db.models import Q, Value, CharField, F
from django.db.models.query import QuerySet
from django.apps import apps

import logging
from collections import OrderedDict

from danceschool.core.signals import (
    request_discounts, apply_discount, apply_addons, post_registration,
    get_eventregistration_data
)
from danceschool.core.constants import getConstant
from danceschool.core.models import Customer, EventRegistration, Registration

from .helpers import getApplicableDiscountCombos
from .models import DiscountCombo, RegistrationDiscount


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(request_discounts)
def getBestDiscount(sender, **kwargs):
    '''
    When a customer registers for events, discounts may need to be
    automatically applied.  A given shopping cart may, in fact,
    be eligible for multiple different types of discounts (e.g. hours-based
    discounts for increasing numbers of class hours), but typically, only one
    discount should be applied.  Therefore, this handler loops through all potential
    discounts, finds the ones that are applicable to the passed registration or set
    of items, and returns the code and discounted price of the best available discount,
    in a tuple of the form (code, discounted_price).
    '''
    if not getConstant('general__discountsEnabled'):
        return

    logger.debug('Signal fired to request discounts.')

    reg = kwargs.pop('registration', None)
    invoice = kwargs.get('invoice', None)
    customer_final = kwargs.pop('customer_final', False)

    if not reg:
        reg = Registration.objects.filter(invoice=invoice).first()

    if not reg or not invoice:
        logger.warning('No registration passed, discounts not applied.')
        return

    payAtDoor = reg.payAtDoor

    # Check if this is a new customer, who may be eligible for special discounts
    newCustomer = True
    customer = Customer.objects.filter(
        email=invoice.email, first_name=invoice.firstName, last_name=invoice.lastName
    ).first()
    if (customer and customer.numEventRegistrations > 0) or not customer_final:
        newCustomer = False

    eligible_filter = (
        Q(event__series__pricingTier__isnull=False) |
        Q(event__publicevent__pricingTier__isnull=False)
    )
    ineligible_filter = (
        (Q(event__series__isnull=False) & Q(event__series__pricingTier__isnull=True)) |
        (Q(event__publicevent__isnull=False) & Q(event__publicevent__pricingTier__isnull=True)) |
        Q(dropIn=True)
    )
    if apps.is_installed('danceschool.private_lessons'):
        eligible_filter = eligible_filter | Q(event__privatelessonevent__pricingTier__isnull=False)
        ineligible_filter = ineligible_filter | (
            Q(event__privatelessonevent__isnull=False) &
            Q(event__privatelessonevent__pricingTier__isnull=True)
        )

    # The items for which the customer registered.
    eventregs_list = reg.eventregistration_set.all()
    eligible_list = eventregs_list.filter(dropIn=False).filter(eligible_filter)
    ineligible_list = eventregs_list.filter(ineligible_filter)

    student = getattr(eligible_list.first(), 'student', False)

    ineligible_total = sum(
        [x.event.getBasePrice(payAtDoor=payAtDoor) for x in ineligible_list.exclude(dropIn=True)] +
        [x.event.getBasePrice(dropIns=1) for x in ineligible_list.filter(dropIn=True)]
    )

    # Get the applicable discounts and sort them in ascending category order
    # so that the best discounts are always listed in the order that they will
    # be applied.
    discountCodesApplicable = getApplicableDiscountCombos(
        eligible_list, newCustomer, student, customer=customer, addOn=False,
        cannotCombine=False, dateTime=reg.dateTime
    )
    discountCodesApplicable.sort(key=lambda x: x.code.category.order)

    # Once we have a list of codes to try, calculate the discounted price for each
    # possibility, and pick the one in each category that has the lowest total
    # price.  We also need to keep track of the way in which some discounts
    # are allocated across individual events.
    best_discounts = OrderedDict()

    initial_prices = [x.event.getBasePrice(payAtDoor=payAtDoor) for x in eligible_list]
    initial_total = sum(initial_prices)

    if discountCodesApplicable:
        net_allocated_prices = initial_prices
        net_precategory_price = initial_total
        last_category = discountCodesApplicable[0].code.category

    for discount in discountCodesApplicable:

        # If the category has changed, then the new net_allocated_prices and the
        # new net_precategory price are whatever was found to be best in the last
        # category.
        if (discount.code.category != last_category):
            last_category = discount.code.category

            if best_discounts:
                # Since this is an OrderedDict, we can get the last element of the dict from
                # the iterator, which is the last category for which there was a valid discount.
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

        response = discount.code.applyAndAllocate(net_allocated_prices, tieredTuples, payAtDoor)

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

    # Now, repeat the basic process for codes that cannot be combined.  These codes are always
    # compared against the base price, and there is no need to allocate across items since
    # only one code will potentially be applied.
    uncombinedCodesApplicable = getApplicableDiscountCombos(
        eligible_list, newCustomer, student,
        customer=customer, addOn=False, cannotCombine=True, dateTime=reg.dateTime
    )

    for discount in uncombinedCodesApplicable:

        # The second item in each tuple is now adjusted, so that each item that is wholly or partially
        # applied against the discount will be wholly (value goes to 0) or partially subtracted from the
        # remaining value to be calculated at full price.
        tieredTuples = [(x, 1) for x in eligible_list[:]]

        for itemTuple in discount.itemTuples:
            tieredTuples = [(p, q) if p != itemTuple[0] else (p, q - itemTuple[1]) for (p, q) in tieredTuples]

        response = discount.code.applyAndAllocate(initial_prices, tieredTuples, payAtDoor)

        # Once the final price has been calculated, apply it iff it is less than
        # the previously best discount or combination of discounts found.
        if (
            response and
            response.net_price < min([x.net_price for x in best_discounts.values()] + [initial_total])
        ):
            best_discounts = OrderedDict({discount.code.category.name: response})

    if not best_discounts:
        logger.debug('No applicable discounts found.')

    # Return the list of discounts to be applied (in DiscountInfo tuples), along with the additional
    # price of ineligible items to be added.
    return DiscountCombo.DiscountApplication([x for x in best_discounts.values()], ineligible_total)


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

    # No need to get all objects, just the ones that could qualify one for an add-on
    cart_object_list = reg.eventregistration_set.filter(dropIn=False).filter(
        Q(event__series__pricingTier__isnull=False) |
        Q(event__publicevent__pricingTier__isnull=False)
    )

    student = getattr(cart_object_list.first(), 'student', False)

    availableAddons = getApplicableDiscountCombos(
        cart_object_list, newCustomer, student,
        customer=customer, addOn=True, dateTime=reg.dateTime
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

    regs = kwargs.pop('eventregistrations', None)
    if not regs or not isinstance(regs, QuerySet) or not (regs.model == EventRegistration):
        logger.warning('No/invalid EventRegistration queryset passed, so discounts not found.')
        return

    extras = {}
    regs = regs.filter(registration__registrationdiscount__isnull=False).prefetch_related(
        'registration__registrationdiscount_set',
        'registration__registrationdiscount_set__discount'
    )

    for reg in regs:
        extras[reg.id] = list(reg.registration.registrationdiscount_set.annotate(
            name=F('discount__name'),
            type=Value('discount', output_field=CharField()),
            amount=F('discountAmount'),
        ).values('id', 'amount', 'name', 'type'))

    return extras
