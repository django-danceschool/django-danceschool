from django.dispatch import receiver
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _

import logging

from danceschool.core.signals import request_discounts, apply_discount, apply_addons, post_registration
from danceschool.core.constants import getConstant
from danceschool.core.models import Customer

from .helpers import getApplicableDiscountCombos
from .models import DiscountCombo, TemporaryRegistrationDiscount, RegistrationDiscount


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(request_discounts)
def getBestDiscount(sender,**kwargs):
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

    reg = kwargs.pop('registration',None)
    if not reg:
        logger.warning('No registration passed, discounts not applied.')
        return

    isStudent = reg.student
    payAtDoor = reg.payAtDoor

    # Check if this is a new customer, who may be eligible for special discounts
    newCustomer = True
    customers = Customer.objects.filter(user__email=reg.email)
    for c in customers:
        if c.numClassSeries > 0:
            newCustomer = False
            break

    # The items for which the customer registered.
    eventregs_list = reg.temporaryeventregistration_set.all()
    eligible_list = eventregs_list.filter(dropIn=False).filter(Q(event__series__pricingTier__isnull=False) | Q(event__publicevent__pricingTier__isnull=False))
    ineligible_list = eventregs_list.filter((Q(event__series__isnull=False) & Q(event__series__pricingTier__isnull=True)) | (Q(event__publicevent__isnull=False) & Q(event__publicevent__pricingTier__isnull=True)) | Q(dropIn=True))

    price_list = [x.event.getBasePrice(isStudent=isStudent,payAtDoor=payAtDoor) for x in eventregs_list]

    ineligible_total = sum([x.event.getBasePrice(isStudent=isStudent,payAtDoor=payAtDoor) for x in ineligible_list])

    discountCodesApplicable = getApplicableDiscountCombos(eligible_list, newCustomer)

    # Once we have a list of codes to try, calculate the discounted price for each possibility,
    # and pick the one that has the lowest total price
    best_price = sum(price_list)
    best_discount_code = None

    for discount in discountCodesApplicable:

        # The second item in each tuple is now adjusted, so that each item that is wholly or partially
        # applied against the discount will be wholly (value goes to 0) or partially subtracted from the
        # remaining value to be calculated at full price.
        tieredTuples = [(x,1) for x in eligible_list[:]]

        for itemTuple in discount.itemTuples:
            tieredTuples = [(p,q) if p != itemTuple[0] else (p,q - itemTuple[1]) for (p,q) in tieredTuples]

        # Now apply the appropriate type of pricing code

        if discount.code.discountType == DiscountCombo.DiscountType.flatPrice:
            # Flat-price for all applicable items (partial application for items which are
            # only partially needed to apply the discount)

            applicable_price = discount.code.getFlatPrice(isStudent,payAtDoor) or 0

            this_price = applicable_price \
                + sum([x[0].event.getBasePrice(isStudent=False,payAtDoor=False) * x[1] if x[1] != 1 else x[0].price for x in tieredTuples]) \
                + ineligible_total

        elif discount.code.discountType == DiscountCombo.DiscountType.dollarDiscount:
            # Discount the set of applicable items by a specific number of dollars (currency units)

            this_price = sum([x[0].price for x in tieredTuples]) \
                + ineligible_total \
                - discount.code.dollarDiscount

        elif discount.code.discountType == DiscountCombo.DiscountType.percentDiscount:
            # Percentage off discounts, which may be applied to all items in the cart,
            # or just to the items that were needed to apply the discount

            if discount.code.percentUniversallyApplied:
                this_price = \
                    (
                        sum([x[0].event.getBasePrice(isStudent=isStudent,payAtDoor=payAtDoor) for x in tieredTuples]) +
                        ineligible_total
                    ) * (100 - max(min(discount.code.percentDiscount,100),0))
            else:
                this_price = sum([x[0].event.getBasePrice(isStudent=isStudent,payAtDoor=payAtDoor) * (1 - x[1]) for x in tieredTuples]) * (100 - max(min(discount.code.percentDiscount,100),0)) \
                    + sum([x[0].event.getBasePrice(isStudent=isStudent,payAtDoor=payAtDoor) * x[1] for x in tieredTuples]) \
                    + ineligible_total
        else:
            raise KeyError(_('Invalid discount type.'))

        # Once the final price has been calculated, apply it iff it is less than
        # the previously best discount found.
        if this_price < best_price:
            best_price = this_price
            best_discount_code = discount.code

    if not best_discount_code:
        logger.debug('No applicable discounts found.')

    return (best_discount_code, best_price)


@receiver(apply_discount)
def applyTemporaryDiscount(sender,**kwargs):
    # Get the registration and the customer
    if not getConstant('general__discountsEnabled'):
        return

    logger.debug('Signal fired to apply discounts.')

    reg = kwargs.pop('registration',None)
    discount = kwargs.pop('discount',None)
    discountAmount = kwargs.pop('discount_amount',None)

    if not reg or not discount:
        logger.warning('Incomplete information passed, discounts not applied.')
        return

    obj = TemporaryRegistrationDiscount.objects.create(
        registration=reg,
        discount=discount,
        discountAmount=discountAmount,
    )
    logger.debug('Discount applied.')
    return obj


@receiver(apply_addons)
def getAddonItems(sender, **kwargs):
    # Check if this is a new customer
    if not getConstant('general__discountsEnabled'):
        return

    logger.debug('Signal fired to request free add-ons.')

    reg = kwargs.pop('registration',None)
    if not reg:
        logger.warning('No registration passed, addons not applied.')
        return

    newCustomer = True
    customers = Customer.objects.filter(user__email=reg.email)
    for c in customers:
        if c.numClassSeries > 0:
            newCustomer = False
            break

    availableAddons = DiscountCombo.objects.filter(discountType=DiscountCombo.DiscountType.addOn,active=True)
    if not newCustomer:
        availableAddons = availableAddons.filter(newCustomersOnly=False)

    # No need to get all objects, just the ones that could qualify one for an add-on
    cart_object_list = reg.temporaryeventregistration_set.filter(dropIn=False).filter(Q(event__series__pricingTier__isnull=False) | Q(event__publicevent__pricingTier__isnull=False))

    # Start out with a blank list of codes and fill the list
    appliedAddons = []

    for x in availableAddons:
        # Create two lists, one that starts with all of the items necessary for the discount to apply,
        # and one that starts empty.  As we find an item in the cart that matches an item in the discount
        # requirements, move the item in the discount requirements from the first list to the second list.
        # If, after all items have been checked, the first list is empty and the second list is full, then
        # the discount is applicable to the cart.  The third list keeps track of the items used to apply
        # the discount.  Note that for addons, it doesn't matter which items are used to apply the addon,
        # since addons do not affect pricing.
        necessary_discount_items = x.getComponentList()[:]
        count_necessary_items = len(necessary_discount_items)
        matched_discount_items = []
        matched_cart_items = []

        # For each item in the cart
        for y in cart_object_list:
            # for each component of the potential discount that has not already been matched
            for j,z in enumerate(necessary_discount_items):
                # If pricing tiers match, then check each of the other attributes.
                # If they all match too, then we have a match, which should be checked off
                if y.event.pricingTier == z.pricingTier:
                    match_flag = True
                    for attribute in ['level','weekday']:
                        if getattr(y.event,attribute) != getattr(z,attribute) and getattr(z,attribute) is not None:
                            match_flag = False
                            break
                    if match_flag:
                        matched_discount_items.append(necessary_discount_items.pop(j))
                        matched_cart_items.append(y)
                        break

        if len(necessary_discount_items) == 0 and len(matched_discount_items) == count_necessary_items:
            appliedAddons += [x]

    return appliedAddons


@receiver(post_registration)
def applyFinalDiscount(sender,**kwargs):
    # Get the registration and the customer
    if not getConstant('general__discountsEnabled'):
        return

    logger.debug('Signal fired to finalize application of discounts.')

    reg = kwargs.pop('registration',None)

    if not reg:
        logger.debug('No registration passed, discounts not applied.')
        return

    trds = TemporaryRegistrationDiscount.objects.filter(registration=reg.temporaryRegistration)

    obj = None
    for temp_discount in trds:
        obj = RegistrationDiscount.objects.create(
            registration=reg,
            discount=temp_discount.discount,
            discountAmount=temp_discount.discountAmount,
        )

    logger.debug('Discounts applied.')
    return obj
