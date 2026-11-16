from ..models import DiscountCategory, DiscountCombo
from .base import DiscountAllocationBase


class DiscountCombiningTest(DiscountAllocationBase):
    '''
    One discount can be applied from each category, in the order of the
    categories, and each discount applies to the price that remains after the
    discounts in prior categories. A discount in a category that cannot be
    combined is only used by itself, and only if that gives the lowest price.
    Each test registers for one $20 series (B) that earns the discounts, and
    most also include a $10 series (A) that does not.
    '''

    def setUp(self):
        super().setUp()
        self.first = DiscountCategory.objects.get(id=1)
        self.second = DiscountCategory.objects.create(
            name='Second Category', order=self.first.order + 1
        )
        self.alone = DiscountCategory.objects.create(
            name='Not Combined', order=self.first.order + 2, cannotCombine=True
        )
        self.s_a = self.create_series(pricingTier=self.tier_a)
        self.s_b = self.create_series(pricingTier=self.tier_b)

    def combo(self, name, category, **kwargs):
        combo = self.make_combo(name=name, **kwargs)
        combo.category = category
        combo.save()
        return combo

    def dollar(self, name, category, amount):
        return self.combo(
            name, category, dollarDiscount=amount,
            discountType=DiscountCombo.DiscountType.dollarDiscount,
        )

    def flat(self, name, category, price):
        return self.combo(
            name, category, onlinePrice=price, doorPrice=price,
            discountType=DiscountCombo.DiscountType.flatPrice,
        )

    def discount_names(self, response):
        return [x[0] for x in response.context_data.get('discount_codes') or []]

    def test_discounts_in_two_categories_both_apply(self):
        ''' 50% off of $20 is $10, and then $4 off of that is $6. '''
        self.combo('Half Off', self.first, percentDiscount=50)
        self.dollar('Four Off', self.second, 4)

        response = self.checkout(self.s_a, self.s_b)

        self.assertEqual(self.discount_names(response), ['Half Off', 'Four Off'])
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 14, places=2)
        self.assertItemTotals(response, self.s_a, [10])
        self.assertItemTotals(response, self.s_b, [6])

    def test_second_percentage_applies_to_reduced_price(self):
        ''' 50% off of $20 is $10, and 50% off of that is $5. '''
        self.combo('Half Off', self.first, percentDiscount=50)
        self.combo('Half Off Again', self.second, percentDiscount=50)

        response = self.checkout(self.s_a, self.s_b)

        self.assertEqual(self.discount_names(response), ['Half Off', 'Half Off Again'])
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 15, places=2)
        self.assertItemTotals(response, self.s_a, [10])
        self.assertItemTotals(response, self.s_b, [5])

    def test_amount_recorded_for_each_discount(self):
        ''' The record of each discount has the amount of that discount only. '''
        half = self.combo('Half Off', self.first, percentDiscount=50)
        four = self.dollar('Four Off', self.second, 4)

        response = self.checkout(self.s_b)
        reg = response.context_data['invoice'].registration

        self.assertAlmostEqual(
            reg.registrationdiscount_set.get(discount=half).discountAmount, 10, places=2
        )
        self.assertAlmostEqual(
            reg.registrationdiscount_set.get(discount=four).discountAmount, 4, places=2
        )

    def test_only_best_discount_in_category_applies(self):
        self.combo('Quarter Off', self.first, percentDiscount=25)
        self.combo('Half Off', self.first, percentDiscount=50)

        response = self.checkout(self.s_b)

        self.assertEqual(self.discount_names(response), ['Half Off'])
        self.assertItemTotals(response, self.s_b, [10])

    def test_flat_price_in_later_category_applies_if_lower(self):
        '''
        A flat price replaces the price from prior categories, when it is
        lower: 25% off of $20 is $15, and the flat price is $12.
        '''
        self.combo('Quarter Off', self.first, percentDiscount=25)
        self.flat('Flat Twelve', self.second, 12)

        response = self.checkout(self.s_a, self.s_b)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 8, places=2)
        self.assertItemTotals(response, self.s_a, [10])
        self.assertItemTotals(response, self.s_b, [12])

    def test_flat_price_in_later_category_ignored_if_higher(self):
        ''' 25% off of $20 is $15, which is less than a flat price of $18. '''
        self.combo('Quarter Off', self.first, percentDiscount=25)
        self.flat('Flat Eighteen', self.second, 18)

        response = self.checkout(self.s_a, self.s_b)

        self.assertEqual(self.discount_names(response), ['Quarter Off'])
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 5, places=2)
        self.assertItemTotals(response, self.s_b, [15])

    def test_uncombined_discount_used_alone_when_it_is_best(self):
        '''
        The discounts that can be combined take $7 off. The discount that
        cannot be combined takes $10 off, so it is used by itself.
        '''
        self.combo('Quarter Off', self.first, percentDiscount=25)
        self.dollar('Two Off', self.second, 2)
        self.combo('Half Off Alone', self.alone, percentDiscount=50)

        response = self.checkout(self.s_a, self.s_b)

        self.assertEqual(self.discount_names(response), ['Half Off Alone'])
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 10, places=2)
        self.assertItemTotals(response, self.s_a, [10])
        self.assertItemTotals(response, self.s_b, [10])

    def test_uncombined_discount_not_used_when_combination_is_better(self):
        '''
        The discounts that can be combined take $7 off. The discount that
        cannot be combined would only take $4 off, so it is not used.
        '''
        self.combo('Quarter Off', self.first, percentDiscount=25)
        self.dollar('Two Off', self.second, 2)
        self.combo('Fifth Off Alone', self.alone, percentDiscount=20)

        response = self.checkout(self.s_a, self.s_b)

        self.assertEqual(self.discount_names(response), ['Quarter Off', 'Two Off'])
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 7, places=2)
        self.assertItemTotals(response, self.s_b, [13])
