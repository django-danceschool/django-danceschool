from django.utils import timezone
from django.db.models import Q

from datetime import timedelta

from .models import DiscountCombo, PointGroup


def getApplicableDiscountCombos(
    cart_object_list, newCustomer=True, student=False, customer=None,
    addOn=False, cannotCombine=False, dateTime=None
):

    # First, identify the set of discounts that could potentially be satisfied
    # based on customer restrictions, active status, and expiration date.
    filters = Q(active=True)
    if customer:
        filters &= (
            Q(
                Q(customerdiscount__isnull=True) &
                Q(customergroupdiscount__isnull=True)
            ) |
            Q(customerdiscount__customer=customer) |
            Q(customergroupdiscount__group__customer=customer)
        )
    else:
        filters &= (
            Q(customerdiscount__isnull=True) &
            Q(customergroupdiscount__isnull=True)
        )

    # Existing customers can't get discounts marked for new customers only.
    # Add-ons are handled separately.
    if addOn:
        filters = filters & Q(discountType=DiscountCombo.DiscountType.addOn)

        availableDiscountCodes = DiscountCombo.objects.filter(
            filters
        ).exclude(expirationDate__lte=timezone.now()).distinct()
    else:
        filters = filters & Q(category__cannotCombine=cannotCombine)

        availableDiscountCodes = DiscountCombo.objects.filter(
            filters
        ).exclude(
            discountType=DiscountCombo.DiscountType.addOn
        ).exclude(
            expirationDate__lte=timezone.now()
        ).distinct()

    if not newCustomer:
        availableDiscountCodes = availableDiscountCodes.exclude(newCustomersOnly=True)
    if not student:
        availableDiscountCodes = availableDiscountCodes.exclude(studentsOnly=True)

    pointbased_cart_object_lists = {}
    pointbased_customer_object_lists = {}
    total_item_points = {}

    for cart_item in cart_object_list:        
        for ptgroup in cart_item.event.pricingTier.pricingtiergroup_set.all():
            this_points = (
                (ptgroup.points or 0) * int(getattr(cart_item.event, 'discountPointsMultiplier', 1))
            )

            total_item_points[cart_item.id] = total_item_points.get(cart_item.id, 0) + this_points

            for y in range(0, this_points):
                pointbased_cart_object_lists[ptgroup.group] = (
                    pointbased_cart_object_lists.get(ptgroup.group, []) + [(cart_item, this_points),]
                )
            if cart_item.customer == customer:
                for y in range(0, this_points):
                    pointbased_customer_object_lists[ptgroup.group] = (
                        pointbased_customer_object_lists.get(ptgroup.group, []) + [(cart_item, this_points),]
                    )

    for k in pointbased_cart_object_lists.keys():
        pointbased_cart_object_lists[k] =[
            p[0] for p in
            sorted(pointbased_cart_object_lists[k], key=lambda x: x[1], reverse=True)
        ]
    for k in pointbased_customer_object_lists.keys():
        pointbased_customer_object_lists[k] =[
            p[0] for p in
            sorted(pointbased_customer_object_lists[k], key=lambda x: x[1], reverse=True)
        ]

    # Discounts that require registration a number of days in advance are evaluated against
    # midnight local time of the day of registration (so that discounts always close at
    # midnight local time).  Because installations may have timezone support enabled or disabled,
    # calculate the threshold time in advance.
    today_midnight = (
        timezone.localtime(timezone.now()) if timezone.is_aware(timezone.now()) else timezone.now()
    ).replace(hour=0, minute=0, second=0, microsecond=0)

    # Look for exact match. If multiple are found, return them all.
    # If one is not found, then make a list of all subsets of cart_object_list
    # and recursively look for matches.  The loop method allows us to look for codes
    # with a level and weekday requirement as well as codes without a level requirement

    # Start out with a blank list of codes and fill the list with namedtuples
    useableCodes = []

    for x in availableDiscountCodes:
        # Create two lists, one that starts with all of the items necessary for
        # the discount to apply, and one that starts empty.  As we find an item
        # in the cart that matches an item in the discount requirements, move
        # the item in the discount requirements from the first list to the
        # second list. If, after all items have been checked, the first list is
        # empty and the second list is full, then the discount is applicable to
        # the cart.  The third list keeps track of the items used to apply
        # the discount.
        necessary_discount_items = x.getComponentList()[:]
        count_necessary_items = len(necessary_discount_items)
        matched_discount_items = []
        matched_cart_items = []

        if x.customerMatchRequired:
            cart_lists = pointbased_customer_object_lists
        else:
            cart_lists = pointbased_cart_object_lists

        for cart_list in cart_lists.values():
            for y in cart_list:
                # for each component of the potential discount that has not already been matched
                for j, z in enumerate(necessary_discount_items):
                    # All items are a match unless shown otherwise below
                    match_flag = True

                    # Check for matches in weekdays and levels:
                    if z.weekday and y.event.weekday != z.weekday:
                        match_flag = False
                    elif (
                        z.level and hasattr(y.event, 'series') and
                        y.event.series.classDescription.danceTypeLevel != z.level
                    ):
                        match_flag = False
                    # Check that if the discount combo requires that all elements be a
                    # certain number of days in the future, that this event begins at least
                    # that many days in the future from the beginning of today.
                    elif (
                        x.daysInAdvanceRequired is not None and
                        y.event.startTime - today_midnight < timedelta(days=x.daysInAdvanceRequired)
                    ):
                        match_flag = False
                    # If the discount combo is only available for the first X registrants,
                    # then check that we don't already have X individuals registered.
                    # This includes temporary Registrations (so too many discounts don't get
                    # handed out if registration is in progress).
                    elif (
                        x.firstXRegistered is not None and
                        y.event.getNumRegistered(
                            includeTemporaryRegs=True, dateTime=dateTime
                        ) > x.firstXRegistered
                    ):
                        match_flag = False

                    # If we found no reason that it's not a match, then it's a match,
                    # and we can move on to the next object in the cart.
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
            additionalItems = []
            for group in fullPointGroupsMatched:
                additionalItems += cart_lists.get(group, [])

            # Return only the unique cart items that matched the combo (not one per point)
            matchedList = list(set(matched_cart_items + additionalItems))

            # An item could match only in part, so find out how many times it matched, and then
            # figure out how many times it could have matched, to determine the fraction
            # that matched.
            matchedTuples = [
                (
                    item,
                    float(matched_cart_items.count(item)) / total_item_points.get(item.id, 0)
                )
                if item not in additionalItems else (item, 1)
                for item in matchedList
            ]
            useableCodes += [x.ApplicableDiscountCode(x, matchedList, matchedTuples)]

    return useableCodes
