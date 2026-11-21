import json

from django.urls import reverse

from danceschool.core.models import EventAddOn, Invoice, Registration

from ..models import PointGroup, PricingTierGroup, DiscountCombo
from .base import DiscountAllocationBase


class DiscountAddOnTest(DiscountAllocationBase):
    '''
    An event with add-ons (e.g. an all-in pass) is charged at its own price,
    which is allocated among the pass and the events it includes. Discounts
    apply to the price that is charged, not to the stand-alone prices of the
    included events.
    '''

    def setUp(self):
        super().setUp()
        self.tier_pass = self.make_tier('Pass Tier', 100)
        self.tier_included = self.make_tier('Included Tier', 50)
        self.group_pass = PointGroup.objects.create(name='Passes only')
        PricingTierGroup.objects.create(
            group=self.group_pass, pricingTier=self.tier_pass, points=5,
        )

        self.s_pass = self.create_series(pricingTier=self.tier_pass)
        self.s_one = self.create_series(pricingTier=self.tier_included)
        self.s_two = self.create_series(pricingTier=self.tier_included)
        for order, included in enumerate([self.s_one, self.s_two]):
            EventAddOn.objects.create(
                event=self.s_pass, addOnEvent=included, order=order,
                allocationType=EventAddOn.AllocationType.fixed,
                allocationAmount=20,
            )

    def test_pass_without_discount(self):
        response = self.checkout(self.s_pass)

        self.assertItemTotals(response, self.s_pass, [60])
        self.assertItemTotals(response, self.s_one, [20])
        self.assertItemTotals(response, self.s_two, [20])
        self.assertAlmostEqual(response.context_data['invoice'].total, 100, places=2)

    def assertPassItems(self, response, gross, totals):
        items = [
            self.items_for(response, event)[0]
            for event in [self.s_pass, self.s_one, self.s_two]
        ]
        for item, this_gross, this_total in zip(items, gross, totals):
            self.assertAlmostEqual(item.grossTotal, this_gross, places=2)
            self.assertAlmostEqual(item.total, this_total, places=2)
        return items[0]

    def test_included_events_keep_their_own_price(self):
        '''
        By design, the item for each included event keeps the event's own
        price ($50) as its gross total, while its total is its share of the
        price of the pass ($20).  The difference is the savings from buying
        the pass instead of the events on their own, which the registration
        summary shows as "Net Savings": $160 of events for $100.
        '''
        response = self.checkout(self.s_pass)

        pass_item = self.assertPassItems(response, [60, 50, 50], [60, 20, 20])
        self.assertAlmostEqual(pass_item.grossTotalWithAllocation, 160, places=2)
        self.assertAlmostEqual(pass_item.netAllocationAdjustment, -60, places=2)
        self.assertContains(response, 'Net Savings')
        self.assertAlmostEqual(response.context_data['invoice'].grossTotal, 160, places=2)

    def test_discount_does_not_change_the_savings(self):
        '''
        A discount on the pass reduces the totals, but not the gross totals or
        the savings from buying the pass.
        '''
        self.make_combo(
            group=self.group_pass, percentDiscount=50, percentUniversallyApplied=True
        )
        response = self.checkout(self.s_pass)

        pass_item = self.assertPassItems(response, [60, 50, 50], [30, 10, 10])
        self.assertAlmostEqual(pass_item.netAllocationAdjustment, -60, places=2)

    def assertDiscounted(self, response, expected):
        '''
        The registrations, the registration and the invoice are discounted
        only when a discount was applied, not because a pass costs less than
        the events that it includes.
        '''
        invoice = Invoice.objects.get(id=response.context_data['invoice'].id)
        registration = Registration.objects.get(invoice=invoice)
        for er in registration.eventregistration_set.all():
            self.assertEqual(er.discounted, expected, er.event)
        self.assertEqual(registration.discounted, expected)
        self.assertEqual(invoice.discounted, expected)

    def test_pass_is_not_discounted(self):
        self.assertDiscounted(self.checkout(self.s_pass), False)

    def test_discounted_pass_is_discounted(self):
        self.make_combo(
            group=self.group_pass, percentDiscount=50, percentUniversallyApplied=True
        )
        response = self.checkout(self.s_pass)
        self.assertDiscounted(response, True)
        invoice = Invoice.objects.get(id=response.context_data['invoice'].id)
        self.assertAlmostEqual(invoice.discountPercentage, 0.5, places=4)

    def test_pass_with_universal_percent_discount(self):
        ''' 50% off of a $100 pass is $50, however the price is allocated. '''
        self.make_combo(
            group=self.group_pass, percentDiscount=50, percentUniversallyApplied=True
        )
        response = self.checkout(self.s_pass)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 50, places=2)
        self.assertItemTotals(response, self.s_pass, [30])
        self.assertItemTotals(response, self.s_one, [10])
        self.assertItemTotals(response, self.s_two, [10])
        self.assertAlmostEqual(response.context_data['invoice'].total, 50, places=2)

    def _pass_discount(self, expected_discount, **kwargs):
        '''
        A pass and the events that it includes are a single item for discount
        purposes. The discount shown in the cart before checkout is the
        discount on the invoice, and it is shared among the pass and the
        included events in proportion to their prices ($60, $20 and $20).
        '''
        self.make_combo(group=self.group_pass, **kwargs)

        response = self.client.post(
            reverse('cart'), content_type='application/json',
            data=json.dumps({'items': [{
                'item_type': 'Event', 'item_id': self.s_pass.id,
                'sku': f'EVENT_{self.s_pass.id}_GENERAL', 'quantity': 1,
            }]}),
        )
        preview = response.json().get('discount_preview') or {}
        self.assertAlmostEqual(preview.get('total_discount'), expected_discount, places=2)

        response = self.checkout(self.s_pass)
        remaining = (100 - expected_discount) / 100

        self.assertAlmostEqual(
            response.context_data['total_discount_amount'], expected_discount, places=2
        )
        self.assertItemTotals(response, self.s_pass, [60 * remaining])
        self.assertItemTotals(response, self.s_one, [20 * remaining])
        self.assertItemTotals(response, self.s_two, [20 * remaining])
        self.assertAlmostEqual(
            response.context_data['invoice'].total, 100 - expected_discount, places=2
        )

    def test_pass_with_targeted_percent_discount(self):
        self._pass_discount(50, percentDiscount=50)

    def test_pass_with_flat_price_discount(self):
        self._pass_discount(
            20, discountType=DiscountCombo.DiscountType.flatPrice,
            onlinePrice=80, doorPrice=80,
        )

    def test_pass_with_dollar_discount(self):
        self._pass_discount(
            30, discountType=DiscountCombo.DiscountType.dollarDiscount,
            dollarDiscount=30,
        )

    def test_included_events_do_not_earn_discounts(self):
        '''
        The events included in a pass are part of the pass, so they do not
        count separately toward a discount for registering for those events.
        '''
        group = PointGroup.objects.create(name='Included events only')
        PricingTierGroup.objects.create(
            group=group, pricingTier=self.tier_included, points=5,
        )
        self.make_combo(group=group, percentDiscount=50)

        response = self.checkout(self.s_pass)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 0, places=2)
        self.assertAlmostEqual(response.context_data['invoice'].total, 100, places=2)

    def test_student_status_applies_to_included_events(self):
        '''
        A student who registers for a pass is also recorded as a student for
        the events that are included with it. A second series is in the cart
        so that the form that asks for the name and student status for each
        registration is used; it has no fields for the included events, which
        take their values from the pass.
        '''
        s_extra = self.create_series(pricingTier=self.tier_b)
        response = self.checkout(self.s_pass, s_extra, student=True)
        reg = response.context_data['invoice'].registration

        self.assertEqual(reg.eventregistration_set.count(), 4)
        self.assertEqual(
            [er.student for er in reg.eventregistration_set.order_by('id')],
            [True, True, True, True]
        )

    def test_pass_with_full_discount_is_not_negative(self):
        self.make_combo(
            group=self.group_pass, percentDiscount=100, percentUniversallyApplied=True
        )
        response = self.checkout(self.s_pass)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 100, places=2)
        self.assertItemTotals(response, self.s_pass, [0])
        self.assertItemTotals(response, self.s_one, [0])
        self.assertItemTotals(response, self.s_two, [0])
        self.assertAlmostEqual(response.context_data['invoice'].total, 0, places=2)
