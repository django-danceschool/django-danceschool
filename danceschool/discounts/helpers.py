from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

from .models import DiscountCombo


def getApplicableDiscountCombos(cart_object_list,newCustomer=True,addOn=False):

    @python_2_unicode_compatible
    class ApplicableDiscountCode(object):
        '''
        An applied discount may not apply to all items in a customer's
        cart, so an instance of this class keeps track of the code
        as well as the items applicable.
        '''

        def __init__(self,code,items,itemTuples=[]):
            self.code = code
            self.items = items

            # For point-based discounts, the second position in the tuple represents what fraction of the
            # points were used from this item to match the discount (1 if the item was counted in its
            # entirety toward the discount). In cases where a discount does not count against an item entirely
            # (e.g. the 9 hours of class discount applied to three four-week classes), the full price for that
            # item will be calculated by multiplying the remaining fraction of points for that item (e.g. 75%
            # in the above example) against the regular (non-student, online registration) price for that item.
            # In practice, this means that a discount on the whole item will never be superceded by a discount
            # on a portion of the item as long as the percentage discounts for more point are always larger
            # than the discounts for fewer points (e.g. additional hours of class are cheaper).
            if itemTuples:
                self.itemTuples = itemTuples
            else:
                self.itemTuples = [(x,1) for x in items]

        def __str__(self):
            return _('ApplicableDiscountCode Object: Applies \'%s\'' % self.code.name)

    # Existing customers can't get discounts marked for new customers only.  Add-ons are handled separately.
    if addOn:
        availableDiscountCodes = DiscountCombo.objects.filter(active=True,discountType=DiscountCombo.DiscountType.addOn)
    else:
        availableDiscountCodes = DiscountCombo.objects.filter(active=True).exclude(discountType=DiscountCombo.DiscountType.addOn)

    if not newCustomer:
        availableDiscountCodes = availableDiscountCodes.exclude(newCustomersOnly=True)

    # Because discounts are point-based, simplify the process of finding these discounts by creating a list
    # of cart items with one entry per point, not just one entry per cart item
    pointbased_cart_object_list = []
    for cart_item in cart_object_list:
        if hasattr(cart_item.event.pricingTier,'pricingtiergroup'):
            for y in range(0,cart_item.event.pricingTier.pricingtiergroup.points or 0):
                pointbased_cart_object_list += [cart_item]
    pointbased_cart_object_list.sort(key=lambda x: x.event.pricingTier.pricingtiergroup.points, reverse=True)

    # Look for exact match. If multiple are found, return them all.
    # If one is not found, then make a list of all subsets of cart_object_list
    # and recursively look for matches.  The loop method allows us to look for codes
    # with a level and weekday requirement as well as codes without a level requirement

    # Start out with a blank list of codes and fill the list
    useableCodes = []

    for x in availableDiscountCodes:
        # Create two lists, one that starts with all of the items necessary for the discount to apply,
        # and one that starts empty.  As we find an item in the cart that matches an item in the discount
        # requirements, move the item in the discount requirements from the first list to the second list.
        # If, after all items have been checked, the first list is empty and the second list is full, then
        # the discount is applicable to the cart.  The third list keeps track of the items used to apply
        # the discount.
        necessary_discount_items = x.getComponentList()[:]
        count_necessary_items = len(necessary_discount_items)
        matched_discount_items = []
        matched_cart_items = []

        # For each item in the cart
        for y in pointbased_cart_object_list:
            # for each component of the potential discount that has not already been matched
            for j,z in enumerate(necessary_discount_items):
                # If pricing tiers match, then check each of the other attributes.
                # If they all match too, then we have a match, which should be checked off
                if y.event.pricingTier.pricingtiergroup.group == z.pointGroup:
                    match_flag = True

                    # Check for matches in weekdays and levels:
                    if z.weekday and y.event.weekday != z.weekday:
                        match_flag = False
                    if z.level and hasattr(y.event,'series') and y.event.series.classDescription.danceTypeLevel != z.level:
                        match_flag = False

                    if match_flag:
                        matched_discount_items.append(necessary_discount_items.pop(j))
                        matched_cart_items.append(y)
                        break

        if len(necessary_discount_items) == 0 and len(matched_discount_items) == count_necessary_items:
            # However, if a component of this discount applies to all items within the same point group
            # (allWithinPointGroup flag is set), then this discount actually matches everything that
            # it actually matched, plus anything else with that same point group.
            fullPointGroupsMatched = [
                m.pointGroup for m in
                x.discountcombocomponent_set.all() if m.allWithinPointGroup
            ]
            additionalItems = [b for b in pointbased_cart_object_list if b.event.pricingTier.pricingtiergroup.group in fullPointGroupsMatched]

            # Return only the unique cart items that matched the combo (not one per point)
            matchedList = list(set(matched_cart_items + additionalItems))

            # An item could match only in part, so find out how many times it matched, and then
            # figure out how many times it could have matched, to determine the fraction
            # that matched.
            matchedTuples = [
                (item, float(matched_cart_items.count(item)) / item.event.pricingTier.pricingtiergroup.points)
                if item not in additionalItems else (item, 1)
                for item in matchedList
            ]

            useableCodes += [ApplicableDiscountCode(x,matchedList,matchedTuples)]

    return useableCodes
