import json

from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from danceschool.core.models import Customer, CustomerGroup

from ..models import (
    PointGroup, PricingTierGroup, DiscountComboComponent, CustomerDiscount,
    CustomerGroupDiscount
)
from .base import DiscountAllocationBase


class DiscountMatchingTest(DiscountAllocationBase):
    '''
    Tests of the rules that determine whether a discount applies to the items
    in a cart, and to which of them. Each registration for a series in pricing
    tier B is $20, and is worth 5 points in point group B.
    '''

    def series_on_weekday(self, weekday):
        ''' A series in pricing tier B that starts on the passed weekday. '''
        start = timezone.localtime(timezone.now()).replace(
            hour=19, minute=0, second=0, microsecond=0
        ) + timedelta(days=7)
        start += timedelta(days=(weekday - start.weekday()) % 7)
        series = self.create_series(pricingTier=self.tier_b, startTime=start)
        self.assertEqual(series.weekday, weekday)
        return series

    # -- Points ---------------------------------------------------------------

    def test_discount_needing_part_of_an_item(self):
        '''
        A discount that needs 12 points uses all of two registrations, and
        2 of the 5 points (40%) of a third. A 50% discount is then 50% off of
        the first two, and 50% off of 40% of the third.
        '''
        series = [self.create_series(pricingTier=self.tier_b) for x in range(3)]
        combo = self.make_combo(percentDiscount=50)
        combo.discountcombocomponent_set.update(quantity=12)

        response = self.checkout(*series)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 24, places=2)
        self.assertItemTotals(response, series[0], [10])
        self.assertItemTotals(response, series[1], [10])
        self.assertItemTotals(response, series[2], [16])

    def test_discount_needing_more_points_than_in_cart(self):
        series = [self.create_series(pricingTier=self.tier_b) for x in range(2)]
        combo = self.make_combo(percentDiscount=50)
        combo.discountcombocomponent_set.update(quantity=12)

        response = self.checkout(*series)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 0, places=2)
        self.assertItemTotals(response, series[0], [20])
        self.assertItemTotals(response, series[1], [20])

    def test_discount_with_two_components(self):
        '''
        A discount with components in two point groups applies only when the
        cart has items for both, and it applies to the items for both.
        '''
        tier_c = self.make_tier('Tier C', 30)
        group_c = PointGroup.objects.create(name='Tier C only')
        PricingTierGroup.objects.create(group=group_c, pricingTier=tier_c, points=5)

        s_b = self.create_series(pricingTier=self.tier_b)
        s_c = self.create_series(pricingTier=tier_c)
        combo = self.make_combo(percentDiscount=50)
        DiscountComboComponent.objects.create(
            discountCombo=combo, pointGroup=group_c, quantity=5,
            allWithinPointGroup=False,
        )

        response = self.checkout(s_b)
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 0, places=2)

        self.new_session()
        response = self.checkout(s_b, s_c)
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 25, places=2)
        self.assertItemTotals(response, s_b, [10])
        self.assertItemTotals(response, s_c, [15])

    def test_drop_in_does_not_earn_discount_in_cart_preview(self):
        '''
        Drop-ins are not eligible for discounts, including in the preview of
        discounts that is shown in the cart before checkout.
        '''
        s_b = self.create_series(pricingTier=self.tier_b)
        s_b.allowDropins = True
        s_b.save()
        self.make_combo(percentDiscount=50)
        self.client.force_login(self.superuser)

        def preview(**kwargs):
            item = {
                'item_type': 'Event', 'item_id': s_b.id,
                'sku': f'EVENT_{s_b.id}_GENERAL', 'quantity': 1,
            }
            item.update(kwargs)
            response = self.client.post(
                reverse('cart'), content_type='application/json',
                data=json.dumps({'items': [item], 'payAtDoor': True}),
            )
            self.assertEqual(response.status_code, 200)
            return response.json().get('discount_preview')

        self.assertAlmostEqual(preview()['total_discount'], 10, places=2)
        self.assertIsNone(preview(dropIn=True))

    # -- Weekday --------------------------------------------------------------

    def _weekday_discount(self, weekday, other_weekday):
        '''
        A discount whose component is limited to a weekday applies to a series
        on that weekday, and not to a series on another weekday. The series on
        the other weekday is first in the cart.
        '''
        s_other = self.series_on_weekday(other_weekday)
        s_match = self.series_on_weekday(weekday)
        combo = self.make_combo(percentDiscount=50)
        combo.discountcombocomponent_set.update(weekday=weekday)

        response = self.checkout(s_other, s_match)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 10, places=2)
        self.assertItemTotals(response, s_other, [20])
        self.assertItemTotals(response, s_match, [10])

    def test_discount_limited_to_tuesday(self):
        self._weekday_discount(1, 3)

    def test_discount_limited_to_monday(self):
        ''' Monday is weekday number 0. '''
        self._weekday_discount(0, 3)

    def test_weekday_discount_does_not_apply_on_other_days(self):
        s_other = self.series_on_weekday(3)
        combo = self.make_combo(percentDiscount=50)
        combo.discountcombocomponent_set.update(weekday=0)

        response = self.checkout(s_other)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 0, places=2)
        self.assertItemTotals(response, s_other, [20])

    # -- Customers ------------------------------------------------------------

    def test_students_only(self):
        s_b = self.create_series(pricingTier=self.tier_b)
        combo = self.make_combo(percentDiscount=50)
        combo.studentsOnly = True
        combo.save()

        response = self.checkout(s_b)
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 0, places=2)

        self.new_session()
        response = self.checkout(s_b, student=True, names=[('A', 'Student')])
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 10, places=2)
        self.assertItemTotals(response, s_b, [10])

    def test_new_customers_only(self):
        '''
        A discount for new customers applies to a customer's first
        registration, and not to a later one.
        '''
        s_one = self.create_series(pricingTier=self.tier_b)
        s_two = self.create_series(pricingTier=self.tier_b)
        combo = self.make_combo(percentDiscount=50)
        combo.newCustomersOnly = True
        combo.save()

        response = self.checkout(s_one)
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 10, places=2)
        self.pay(response)

        self.new_session()
        response = self.checkout(s_two)
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 0, places=2)
        self.assertItemTotals(response, s_two, [20])

    def test_first_registrants_only(self):
        '''
        A discount for the first person to register applies to the first
        person, and not to the second.
        '''
        s_b = self.create_series(pricingTier=self.tier_b)
        combo = self.make_combo(percentDiscount=50)
        combo.firstXRegistered = 1
        combo.save()

        response = self.checkout(s_b, names=[('First', 'Person')])
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 10, places=2)
        self.pay(response)

        self.new_session()
        response = self.checkout(s_b, names=[('Second', 'Person')])
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 0, places=2)
        self.assertItemTotals(response, s_b, [20])

    def test_first_two_registrants(self):
        s_b = self.create_series(pricingTier=self.tier_b)
        combo = self.make_combo(percentDiscount=50)
        combo.firstXRegistered = 2
        combo.save()

        for name, expected in [('First', 10), ('Second', 10), ('Third', 0)]:
            self.new_session()
            response = self.checkout(s_b, names=[(name, 'Person')])
            self.assertAlmostEqual(
                response.context_data['total_discount_amount'], expected, places=2,
                msg='Discount for the %s person to register' % name.lower()
            )
            self.pay(response)

    def _customer_discount(self, restrict):
        '''
        A discount that is restricted to a customer (or a group of customers)
        applies to that customer, and not to anyone else. The restrict
        argument is a function that takes the discount and the customer.
        '''
        s_b = self.create_series(pricingTier=self.tier_b)
        combo = self.make_combo(percentDiscount=50)
        customer = Customer.objects.create(
            first_name='Special', last_name='Customer', email='mixed@cart.com'
        )
        restrict(combo, customer)

        response = self.checkout(s_b, names=[('Other', 'Person')])
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 0, places=2)

        self.new_session()
        response = self.checkout(s_b, names=[('Special', 'Customer')])
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 10, places=2)
        self.assertItemTotals(response, s_b, [10])

    def test_discount_for_specific_customer(self):
        self._customer_discount(
            lambda combo, customer: CustomerDiscount.objects.create(
                customer=customer, discountCombo=combo
            )
        )

    def test_discount_for_customer_group(self):
        def restrict(combo, customer):
            group = CustomerGroup.objects.create(name='Special Group')
            customer.groups.add(group)
            CustomerGroupDiscount.objects.create(group=group, discountCombo=combo)

        self._customer_discount(restrict)

    def test_customer_match_required(self):
        '''
        A discount that requires registrations to match the invoice only
        counts the registrations of the person named on the invoice. Here,
        the discount needs two registrations.
        '''
        self.gp['registration__multiRegSeriesRule'] = 'Y'
        s_one = self.create_series(pricingTier=self.tier_b)
        s_two = self.create_series(pricingTier=self.tier_b)
        combo = self.make_combo(percentDiscount=50)
        combo.customerMatchRequired = True
        combo.save()
        combo.discountcombocomponent_set.update(quantity=10)

        # One registration for each of two people.
        response = self.checkout(
            s_one, s_two, names=[('First', 'Person'), ('Second', 'Person')]
        )
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 0, places=2)

        # Two registrations for the person named on the invoice.
        self.new_session()
        response = self.checkout(s_one, s_two, names=[('Third', 'Person')])
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 20, places=2)
        self.assertItemTotals(response, s_one, [10])
        self.assertItemTotals(response, s_two, [10])
