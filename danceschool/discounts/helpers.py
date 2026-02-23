
from django.utils import timezone
from django.db.models import Q, Value, F, FloatField, IntegerField, Count
from django.db.models.functions import Coalesce, Cast
from django.apps import apps

from datetime import timedelta
import logging
import re

from danceschool.core.models import Registration, Event


# Define logger for this file
logger = logging.getLogger(__name__)


def prepareCartObjects(reg=None, invoice=None, cart_items=[], payAtDoor=False):
    '''
    This common function is used to prepare the cart for finding the best
    discount available, and also to check whether a specific discount is
    applicable to a specific cart.
    '''

    # To avoid circular import
    from danceschool.discounts.models import PricingTierGroup

    def _get_coalesced(
            elements: dict = {'tier': 'pricingTier'}, qs_class=Event
        ):
        '''
        Get attributs for an event (such as pricing tiers) from the polymorphic
        child class.
        '''
        filter_base = '' if qs_class == Event else 'event__'
        response = {}
        for key,attr in elements.items():
            to_coalesce = [
                F(f'{filter_base}publicevent__{attr}'),
                F(f'{filter_base}series__{attr}')
            ]
            if apps.is_installed('danceschool.private_lessons'):
                to_coalesce.append(F(f'{filter_base}privatelessonevent__{attr}'))
            response[key] = Coalesce(*to_coalesce)
        return response

    if invoice and (not reg):
        reg = Registration.objects.filter(invoice=invoice).first()

    if reg:
        if apps.is_installed('danceschool.private_lessons'):
            quantity_expression = Coalesce(
                Count('event__privatelessonevent__instructoravailability'),
                Value(1),
                output_field=IntegerField()
            )
        else:
            quantity_expression = Value(1)

        # Construct the queryset and then iterate through to construct list of
        # dictionaries. This ensures that the actual event is attached.
        qs = reg.eventregistration_set.select_related(
            'invoiceItem', 'event',
            'event__series__classDescription__danceTypeLevel'
        ).prefetch_related(
            'event__eventoccurrence_set', 'event__eventregistration_set',
            'event__eventregistration_set__registration'
        ).annotate(
            quantity=quantity_expression,
            base_price=Coalesce(
                Cast(
                    F('invoiceItem__data___initialTotal'),
                    output_field=FloatField()
                ),
                F('invoiceItem__grossTotal'),
                output_field=FloatField()
            ),
            _customer_id=F('customer__id'),
            **_get_coalesced(qs_class=reg.eventregistration_set.model)
        )
        event_count_list = [
            {
                'event_id': x.event.id, 'event': x.event,
                'quantity': x.quantity, 'dropIn': x.dropIn,
                'customer_id': x._customer_id, 'tier': x.tier,
                'base_price': x.base_price
            }
            for x in qs
        ]
    elif cart_items:
        events = Event.objects.filter(
            id__in=[x.get('item_id') for x in cart_items]
        ).prefetch_related(
            'eventoccurrence_set', 'eventregistration_set',
            'eventregistration_set__registration'
        ).annotate(
            **_get_coalesced({
                'tier': 'pricingTier',
                'doorPrice': 'pricingTier__doorPrice',
                'onlinePrice': 'pricingTier__onlinePrice',
                'dropinPrice': 'pricingTier__dropinPrice'
            })
        )

        # TODO: Implement logic checking for door registration prior to this
        # function being called.

        event_count_list = [
            {
                'event_id': x.get('item_id'),
                'quantity': x.get('quantity'),
                'dropIn': x.get('drop_in'),
                'customer_id': None
            } for x in cart_items
        ]

        map_events = {x.id: x for x in events}

        for item in event_count_list:
            mapped = map_events.get(item['event_id'])
            if not mapped:
                continue
            # Add pricing tier and base price to the list of event quantities.
            item['event'] = mapped
            item['tier'] = mapped.tier
            if item.get('dropIn', False):
                item['base_price'] = mapped.dropInPrice
            elif payAtDoor:
                item['base_price'] = mapped.doorPrice
            else:
                item['base_price'] = mapped.onlinePrice
    else:
        logger.warning('No registration information passed, discounts not applied.')
        return

    # Split items into eligible (for discounts) and ineligible
    eligible_items = [
        x for x in event_count_list
        if x.get('tier') and (not x.get('dropIn', False))
    ]
    ineligible_total = sum([
        x.get('base_price', 0) for x in event_count_list
        if (x.get('tier') is None) or (x.get('dropIn', False))
    ])

    # Get all point groups and all point amounts based on pricing tier for
    # any events associated with this cart or registration.
    tier_groups = PricingTierGroup.objects.filter(
        pricingTier__in=[x['tier'] for x in eligible_items]
    ).values('pricingTier', 'group', 'points')
    group_ids = set([x.get('group') for x in tier_groups])

    tier_points = {}
    for tier_group in tier_groups:
        this_tier_points = tier_points.get(tier_group['pricingTier'], {})
        this_tier_points[f'group_{tier_group.get("group")}_points'] = tier_group.get('points', 0)
        tier_points[tier_group['pricingTier']] = this_tier_points

    # Merge on total points for each item based on the pricing tier, and then
    # update based on quantity.
    for item in eligible_items:
        this_tier_points = tier_points.get(item['tier'])
        if this_tier_points:
            item.update(this_tier_points)
        for group_id in group_ids:
            item[f'group_{group_id}_points'] = (
                item.get(f'group_{group_id}_points', 0) *
                item.get('quantity', 1)
            )

    # TODO: Student status
    # student = getattr(eligible_it.first(), 'student', False)
    return {
        'cart_object_list': eligible_items,
        'ineligible_total': ineligible_total
    }


def checkDiscountCombos(
    discounts_to_check=[], cart_object_list=[], customer=None, dateTime=None
):
    '''
    Check whether points are satisfied for one or more discounts. Note that this
    is just one step in the validation process. Use
    DiscountCombo.validateForCart() to perform a full validation of a specific
    discount against a specific cart.
    '''

    def unique_dicts(dicts, keys):
        ''' Used below to make a list of dictionaries unique. '''
        seen = set()
        unique = []
        for d in dicts:
            key = tuple(d[k] for k in keys)
            if key not in seen:
                seen.add(key)
                unique.append(d)
        return unique

    if not dateTime:
        dateTime=timezone.now()

    # For each point group, construct a list of [(cart_item, points)]. First,
    # get the set of possible point groups.
    point_groups = set()
    for cart_item in cart_object_list:
        for key in cart_item.keys():
            match = re.match(r'group_([0-9]+)_points', key)
            if match:
                point_groups.add(int(match.group(1)))

    # Initialize dictionaries to populate below.
    pointbased_cart_object_lists = {ptgroup: [] for ptgroup in point_groups}
    pointbased_customer_object_lists = {ptgroup: [] for ptgroup in point_groups}
    total_item_points = {
        cart_item.get('event_id'): 0 for cart_item in cart_object_list
    }

    # Now loop through items to populate the dictionaries.
    for cart_item in cart_object_list:
        event_id = cart_item.get('event_id')

        for ptgroup in point_groups:
            this_points = cart_item.get(f'group_{ptgroup}_points', 0)
            total_item_points[event_id] += this_points

            for y in range(0, this_points):
                pointbased_cart_object_lists[ptgroup].append((cart_item, this_points))
            if customer and (cart_item.get('customer_id') == customer.id):
                for y in range(0, this_points):
                    pointbased_customer_object_lists[ptgroup].append((cart_item, this_points))

    # Sort the point-based lists in descending order of point values so that the
    # most "valuable" items toward any discount are listed first.
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
        timezone.localtime(timezone.now())
        if timezone.is_aware(timezone.now())
        else timezone.now()
    ).replace(hour=0, minute=0, second=0, microsecond=0)

    # Look for exact match. If multiple are found, return them all.
    # If one is not found, then make a list of all subsets of cart_object_list
    # and recursively look for matches.  The loop method allows us to look for codes
    # with a level and weekday requirement as well as codes without a level requirement

    # Start out with a blank list of codes and fill the list with namedtuples
    useableCodes = []

    for x in discounts_to_check:
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

        for p, cart_list in cart_lists.items():
            for y in cart_list:
                # for each component of the potential discount that has not already been matched
                for j, z in enumerate(necessary_discount_items):
                    # All items are a match unless shown otherwise below
                    match_flag = True

                    # Check that this component requires this type of points.
                    if z.pointGroup.id != p:
                        match_flag = False

                    # Check for matches in weekdays and levels:
                    elif z.weekday and y['event'].weekday != z.weekday:
                        match_flag = False
                    elif (
                        z.level and hasattr(y['event'], 'series') and
                        y.event.series.classDescription.danceTypeLevel != z.level
                    ):
                        match_flag = False
                    # Check that if the discount combo requires that all elements be a
                    # certain number of days in the future, that this event begins at least
                    # that many days in the future from the beginning of today.
                    elif (
                        x.daysInAdvanceRequired is not None and
                        y['event'].startTime - today_midnight < timedelta(days=x.daysInAdvanceRequired)
                    ):
                        match_flag = False
                    # If the discount combo is only available for the first X registrants,
                    # then check that we don't already have X individuals registered.
                    # This includes temporary Registrations (so too many discounts don't get
                    # handed out if registration is in progress).
                    elif (
                        x.firstXRegistered is not None and
                        y['event'].getNumRegistered(
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

        if (
            len(necessary_discount_items) == 0 and
            len(matched_discount_items) == count_necessary_items
        ):
            # However, if a component of this discount applies to all items
            # within the same point group (allWithinPointGroup flag is set),
            # then this discount actually matches everything that it actually
            # matched, plus anything else with that same point group.
            fullPointGroupsMatched = [
                m.pointGroup.id for m in
                x.discountcombocomponent_set.all() if m.allWithinPointGroup
            ]
            additionalItems = []
            for group in fullPointGroupsMatched:
                additionalItems += cart_lists.get(group, [])

            # Return only the unique cart items that matched the combo (not one
            # per point)
            matchedList = unique_dicts(
                matched_cart_items + additionalItems,
                keys=['event_id', 'quantity', 'dropIn', 'customer_id']
            )

            # An item could match only in part, so find out how many times it
            # matched, and then figure out how many times it could have matched,
            # to determine the fraction that matched.
            matchedTuples = [
                (
                    item,
                    float(matched_cart_items.count(item)) /
                    total_item_points.get(item.get('event_id'), 0)
                )
                if item not in additionalItems else (item, 1)
                for item in matchedList
            ]
            useableCodes += [
                x.ApplicableDiscountCode(x, matchedList, matchedTuples)
            ]

    # Return the list of codes that matched.
    return useableCodes


def getApplicableDiscountCombos(
    cart_object_list=[], newCustomer=True, student=False, customer=None,
    addOn=False, cannotCombine=False, dateTime=None, payAtDoor=False,
    voucher_code=None
):

    # Loaded here to avoid circular import
    from danceschool.discounts.models import DiscountCombo

    # First, identify the set of discounts that could potentially be satisfied
    # based on customer restrictions, active status, expiration date, and passed
    # voucher ID.
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

    if voucher_code:
        filters &= (
            Q(voucherId__isnull=True) |
            Q(voucherId=voucher_code)
        )
    else:
        filters &= Q(voucherId__isnull=True)

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

    if payAtDoor:
        availableDiscountCodes = availableDiscountCodes.exclude(availableAtDoor=False)
    else:
        availableDiscountCodes = availableDiscountCodes.exclude(availableOnline=False)

    if not newCustomer:
        availableDiscountCodes = availableDiscountCodes.exclude(newCustomersOnly=True)
    if not student:
        availableDiscountCodes = availableDiscountCodes.exclude(studentsOnly=True)

    return checkDiscountCombos(
        availableDiscountCodes, cart_object_list, customer, dateTime
    )
