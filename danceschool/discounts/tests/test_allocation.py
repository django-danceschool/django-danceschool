import json

from django.urls import reverse

from danceschool.core.constants import REG_VALIDATION_STR, updateConstant
from danceschool.core.tests.test_tax import TaxTestMixin
from danceschool.core.models import Invoice, PricingTier, Registration

from ..models import (
    PointGroup, PricingTierGroup, DiscountCategory, DiscountCombo, DiscountComboComponent
)
from .base import BaseDiscountsTest, DiscountAllocationBase


class MixedCartDiscountAllocationTest(BaseDiscountsTest):
    '''
    Reproduces a bug where a discount that applies to only some items in a
    mixed cart is allocated proportionally across ALL items by grossTotal,
    rather than being attributed to the items the discount actually covered.

    Scenario: cart contains a $10 regular series + a $20 series eligible for
    a 100% discount. Expected per-item totals after discount: $10 and $0.
    Buggy current behavior allocates the $20 discount as $6.67 off the $10
    item and $13.33 off the $20 item, leaving misleading per-item totals
    (and a wrong grand total once items have different tax rates).
    '''

    def _make_tier(self, name, price):
        return PricingTier.objects.create(
            name=name, onlinePrice=price, doorPrice=price, dropinPrice=price,
        )

    def _make_full_off_combo(self, point_group, name):
        # Uses percentDiscount (non-universal) so the discount attributes
        # to specifically-covered items rather than spreading across the
        # whole cart. flatPrice and dollarDiscount currently spread
        # proportionally (see DiscountCombo.applyAndAllocate); that's a
        # separate concern from this test.
        combo = DiscountCombo.objects.create(
            name=name,
            category=DiscountCategory.objects.get(id=1),
            discountType=DiscountCombo.DiscountType.percentDiscount,
            percentDiscount=100,
            percentUniversallyApplied=False,
            active=True,
            availableOnline=True,
            availableAtDoor=True,
        )
        DiscountComboComponent.objects.create(
            discountCombo=combo, pointGroup=point_group, quantity=5,
            allWithinPointGroup=False,
        )
        return combo

    def test_full_discount_on_one_item_does_not_affect_other_items(self):
        updateConstant('general__discountsEnabled', True)

        tier_a = self._make_tier('Cheap Tier', 10)
        tier_b = self._make_tier('Pricey Tier', 20)

        # Series A is ineligible for the discount; series B is the only
        # member of the point group the discount requires.
        s_a = self.create_series(pricingTier=tier_a)
        s_b = self.create_series(pricingTier=tier_b)

        b_only_group = PointGroup.objects.create(name='Tier B only')
        PricingTierGroup.objects.create(
            group=b_only_group, pricingTier=tier_b, points=5,
        )
        self._make_full_off_combo(b_only_group, 'Free Tier B')

        cart_data = {
            'items': [
                {
                    'item_type': 'Event', 'item_id': s_a.id,
                    'sku': f'EVENT_{s_a.id}_GENERAL', 'quantity': 1,
                },
                {
                    'item_type': 'Event', 'item_id': s_b.id,
                    'sku': f'EVENT_{s_b.id}_GENERAL', 'quantity': 1,
                },
            ],
            'checkout': True,
        }
        response = self.client.post(
            reverse('cart'),
            data=json.dumps(cart_data),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Mixed',
            'lastName': 'Cart',
            'email': 'mixed@cart.com',
            'agreeToPolicies': True,
        }, follow=True)
        # Two items in the cart → flow detours through the multi-customer
        # name form before reaching the summary page.
        self.assertEqual(
            response.redirect_chain, [(reverse('multiRegNameInfo'), 302)],
        )

        invoice_pre = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR].get('invoice_id')
        )
        reg_pre = Registration.objects.get(invoice=invoice_pre)
        name_post = {}
        for er in reg_pre.eventregistration_set.all():
            name_post['er_%s_firstName' % er.id] = 'Mixed'
            name_post['er_%s_lastName' % er.id] = 'Cart'
            name_post['er_%s_email' % er.id] = 'mixed@cart.com'

        response = self.client.post(
            reverse('multiRegNameInfo'), name_post, follow=True,
        )
        self.assertEqual(
            response.redirect_chain, [(reverse('showRegSummary'), 302)],
        )

        invoice = response.context_data.get('invoice')
        items = {it.grossTotal: it for it in invoice.invoiceitem_set.all()}

        # Sanity: the right items exist with the right gross totals.
        self.assertIn(10, items, 'Series A item with grossTotal $10 missing')
        self.assertIn(20, items, 'Series B item with grossTotal $20 missing')
        item_a = items[10]
        item_b = items[20]

        # Invoice grand total must be $10 (the regular item) regardless.
        # Use assertAlmostEqual for floating-point money math.
        self.assertAlmostEqual(
            invoice.total, 10, places=2,
            msg='Invoice total wrong after applying $20 discount to a $20 item',
        )
        self.assertEqual(
            response.context_data.get('total_discount_amount'), 20,
        )

        # The discount applied only to item B, so item A must keep its
        # full $10 total and item B must be reduced to $0.
        self.assertAlmostEqual(
            item_a.total, 10, places=2,
            msg=(
                'Item A (regular $10) should not be discounted; '
                'got {0} (suggests proportional allocation bug)'
            ).format(item_a.total),
        )
        self.assertAlmostEqual(
            item_b.total, 0, places=2,
            msg=(
                'Item B (eligible for 100% off) should be $0; '
                'got {0} (suggests proportional allocation bug)'
            ).format(item_b.total),
        )


class DiscountAllocationTest(DiscountAllocationBase):
    '''
    A discount must reduce the price of the invoice items that earned it, and
    no others (unless it is a universally-applied percentage discount). Each
    test puts a $10 series that earns no discount (A) in the cart along with
    one or more registrations for a series that does (B).
    '''

    def test_two_registrations_for_same_event(self):
        '''
        Two people register for the discounted series on one invoice. Both of
        their items are discounted, and the other item is not.
        '''
        self.gp['registration__multiRegSeriesRule'] = 'Y'
        s_a = self.create_series(pricingTier=self.tier_a)
        s_b = self.create_series(pricingTier=self.tier_b)
        self.make_combo(percentDiscount=50, allWithinPointGroup=True)

        response = self.checkout(
            s_a, s_b, s_b, names=[('First', 'Person'), ('Second', 'Person')]
        )

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 20, places=2)
        self.assertItemTotals(response, s_a, [10])
        self.assertItemTotals(response, s_b, [10, 10])
        self.assertAlmostEqual(response.context_data['invoice'].total, 30, places=2)

    def _two_registrations_one_discount(self, names):
        '''
        A discount that is earned by one registration applies once to an
        invoice, and it applies in full to the first registration.
        '''
        self.gp['registration__multiRegSeriesRule'] = 'Y'
        s_b = self.create_series(pricingTier=self.tier_b)
        self.make_combo(percentDiscount=50)

        response = self.checkout(s_b, s_b, names=names)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 10, places=2)
        self.assertItemTotals(response, s_b, [10, 20])
        self.assertAlmostEqual(response.context_data['invoice'].total, 30, places=2)

    def test_discount_applies_once_for_two_different_people(self):
        self._two_registrations_one_discount(
            [('First', 'Person'), ('Second', 'Person')]
        )

    def test_discount_applies_once_for_same_person_twice(self):
        self._two_registrations_one_discount([('First', 'Person')])

    def test_discount_goes_to_first_customer_when_customers_alternate(self):
        '''
        Two people each register for two series, and their registrations
        alternate. A discount that is earned by two registrations goes to
        both of the first person's registrations, and it is not split between
        the two people.
        '''
        self.gp['registration__multiRegSeriesRule'] = 'Y'
        s_one = self.create_series(pricingTier=self.tier_b)
        s_two = self.create_series(pricingTier=self.tier_b)
        combo = self.make_combo(percentDiscount=50)
        combo.discountcombocomponent_set.update(quantity=10)

        response = self.checkout(
            s_one, s_one, s_two, s_two,
            names=[('First', 'Person'), ('Second', 'Person')],
        )

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 20, places=2)
        self.assertItemTotals(response, s_one, [10, 20])
        self.assertItemTotals(response, s_two, [10, 20])

    def test_discount_limited_to_level(self):
        '''
        A discount whose component is limited to a class level only applies
        to a series at that level.
        '''
        s_one = self.create_series(
            pricingTier=self.tier_b, classDescription=self.levelOneClassDescription
        )
        s_two = self.create_series(
            pricingTier=self.tier_b, classDescription=self.levelTwoClassDescription
        )
        combo = self.make_combo(percentDiscount=50)
        combo.discountcombocomponent_set.update(level=self.levelTwo)

        response = self.checkout(s_one, s_two)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 10, places=2)
        self.assertItemTotals(response, s_one, [20])
        self.assertItemTotals(response, s_two, [10])

    def test_dollar_discount_is_targeted(self):
        s_a = self.create_series(pricingTier=self.tier_a)
        s_b = self.create_series(pricingTier=self.tier_b)
        self.make_combo(
            discountType=DiscountCombo.DiscountType.dollarDiscount, dollarDiscount=5,
        )

        response = self.checkout(s_a, s_b)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 5, places=2)
        self.assertItemTotals(response, s_a, [10])
        self.assertItemTotals(response, s_b, [15])
        self.assertAlmostEqual(response.context_data['invoice'].total, 25, places=2)

    def test_flat_price_discount_is_targeted(self):
        s_a = self.create_series(pricingTier=self.tier_a)
        s_b = self.create_series(pricingTier=self.tier_b)
        self.make_combo(
            discountType=DiscountCombo.DiscountType.flatPrice,
            onlinePrice=12, doorPrice=12,
        )

        response = self.checkout(s_a, s_b)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 8, places=2)
        self.assertItemTotals(response, s_a, [10])
        self.assertItemTotals(response, s_b, [12])
        self.assertAlmostEqual(response.context_data['invoice'].total, 22, places=2)

    def test_universal_percent_discount_applies_to_all_items(self):
        '''
        A percentage discount that is universally applied reduces every
        eligible item, including the ones that did not earn it.
        '''
        s_a = self.create_series(pricingTier=self.tier_a)
        s_b = self.create_series(pricingTier=self.tier_b)
        self.make_combo(percentDiscount=50, percentUniversallyApplied=True)

        response = self.checkout(s_a, s_b)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 15, places=2)
        self.assertItemTotals(response, s_a, [5])
        self.assertItemTotals(response, s_b, [10])
        self.assertAlmostEqual(response.context_data['invoice'].total, 15, places=2)

    def test_summary_page_reload_gives_same_totals(self):
        s_a = self.create_series(pricingTier=self.tier_a)
        s_b = self.create_series(pricingTier=self.tier_b)
        self.make_combo(percentDiscount=50)

        response = self.checkout(s_a, s_b)
        self.assertItemTotals(response, s_a, [10])
        self.assertItemTotals(response, s_b, [10])

        response = self.client.get(reverse('showRegSummary'))
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 10, places=2)
        self.assertItemTotals(response, s_a, [10])
        self.assertItemTotals(response, s_b, [10])
        self.assertAlmostEqual(response.context_data['invoice'].total, 20, places=2)


class DiscountAllocationTaxTest(TaxTestMixin, DiscountAllocationBase):
    '''
    Tax is calculated for each invoice item at its own rate, so the tax on an
    invoice is only correct if a discount is taken off the correct items.
    Series A is taxed at 10%, and series B (which earns a 50% discount) takes
    place in another jurisdiction, where it is taxed at 3%.
    '''

    def setUp(self):
        super().setUp()
        self.setUpTax()
        self.s_a = self.create_series(pricingTier=self.tier_a)
        self.s_b = self.create_series(
            pricingTier=self.tier_b, location=self.otherLocation
        )
        self.make_combo(percentDiscount=50)

    def tearDown(self):
        super().tearDown()
        self.gp['registration__buyerPaysSalesTax'] = True
        self.tearDownTax()

    def assertTaxes(self, response, expected_a, expected_b):
        item_a = self.items_for(response, self.s_a)[0]
        item_b = self.items_for(response, self.s_b)[0]
        invoice = Invoice.objects.get(id=response.context_data['invoice'].id)

        self.assertEqual(item_a.taxRate, self.SERIES_RATE)
        self.assertEqual(item_b.taxRate, self.OTHER_RATE)
        self.assertItemTotals(response, self.s_a, [10])
        self.assertItemTotals(response, self.s_b, [10])
        self.assertAlmostEqual(item_a.taxes, expected_a, places=4)
        self.assertAlmostEqual(item_b.taxes, expected_b, places=4)
        self.assertAlmostEqual(invoice.taxes, expected_a + expected_b, places=4)
        return invoice

    def test_tax_follows_discount_when_buyer_pays(self):
        self.gp['registration__buyerPaysSalesTax'] = True
        response = self.checkout(self.s_a, self.s_b)

        # 10% of $10, and 3% of the discounted price of $10.
        invoice = self.assertTaxes(response, 1.0, 0.3)
        self.assertAlmostEqual(invoice.outstandingBalance, 21.3, places=4)

    def test_tax_follows_discount_when_seller_pays(self):
        self.gp['registration__buyerPaysSalesTax'] = False
        response = self.checkout(self.s_a, self.s_b)

        # The price includes the tax.
        invoice = self.assertTaxes(response, 10 * 0.1 / 1.1, 10 * 0.03 / 1.03)
        self.assertAlmostEqual(invoice.outstandingBalance, 20, places=4)
