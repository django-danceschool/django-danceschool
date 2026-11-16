from unittest import expectedFailure

from django.test import SimpleTestCase
from django.urls import reverse

from ..handlers import reportDiscounts
from ..models import DiscountCombo, RegistrationDiscount
from .base import DiscountAllocationBase


class AllocateToMatchedTest(SimpleTestCase):
    '''
    DiscountCombo.allocateToMatched() divides a discounted price among items,
    given the price of each item and the fraction of each item that was
    needed for the discount (1 if the item was needed in its entirety).
    '''

    def allocate(self, prices, fractions, net_price):
        return DiscountCombo.allocateToMatched(prices, fractions, net_price)

    def assertAllocation(self, result, expected):
        self.assertEqual(len(result), len(expected))
        for this_result, this_expected in zip(result, expected):
            self.assertAlmostEqual(this_result, this_expected, places=4)

    def test_discount_comes_off_of_matched_item(self):
        self.assertAllocation(self.allocate([10, 20], [0, 1], 25), [10, 15])

    def test_discount_shared_by_matched_items_in_proportion_to_price(self):
        self.assertAllocation(self.allocate([10, 30], [1, 1], 20), [5, 15])

    def test_unmatched_portion_of_item_keeps_its_price(self):
        '''
        The first item was needed in full ($20), and half of the second was
        needed ($10), so the discount of $10 is shared between them 2 to 1.
        '''
        self.assertAllocation(
            self.allocate([20, 20], [1, 0.5], 30), [20 - (20 / 3), 20 - (10 / 3)]
        )

    def test_discount_larger_than_matched_items(self):
        '''
        The matched item becomes free, and the rest of the discount comes
        off of the other item.
        '''
        self.assertAllocation(self.allocate([10, 20], [0, 1], 5), [5, 0])

    def test_nothing_matched_is_allocated_in_proportion_to_price(self):
        self.assertAllocation(self.allocate([10, 20], [0, 0], 15), [5, 10])

    def test_free_items(self):
        self.assertAllocation(self.allocate([0, 0], [1, 0], 0), [0, 0])


class DiscountRecordsTest(DiscountAllocationBase):
    '''
    A record is kept of each discount that is applied to a registration.
    '''

    def setUp(self):
        super().setUp()
        self.s_a = self.create_series(pricingTier=self.tier_a)
        self.s_b = self.create_series(pricingTier=self.tier_b)

    def test_record_is_finalized_when_invoice_is_paid(self):
        combo = self.make_combo(percentDiscount=50)

        response = self.checkout(self.s_a, self.s_b)
        reg = response.context_data['invoice'].registration
        record = RegistrationDiscount.objects.get(registration=reg)

        self.assertEqual(record.discount, combo)
        self.assertAlmostEqual(record.discountAmount, 10, places=2)
        self.assertFalse(record.applied)

        invoice = self.pay(response)
        record = RegistrationDiscount.objects.get(registration=invoice.registration)

        self.assertTrue(invoice.registration.final)
        self.assertTrue(record.applied)
        self.assertAlmostEqual(record.discountAmount, 10, places=2)

    def test_record_is_not_duplicated_when_summary_is_reloaded(self):
        self.make_combo(percentDiscount=50)

        response = self.checkout(self.s_a, self.s_b)
        self.client.get(reverse('showRegSummary'))
        reg = response.context_data['invoice'].registration

        self.assertEqual(RegistrationDiscount.objects.filter(registration=reg).count(), 1)

    # A record is created each time that the summary page finds a discount,
    # but nothing removes the record if the discount no longer applies when
    # the page is loaded again. The stale record is then marked as applied
    # when the invoice is paid, and it is counted in discount statistics.
    @expectedFailure
    def test_record_is_removed_when_discount_no_longer_applies(self):
        combo = self.make_combo(percentDiscount=50)

        response = self.checkout(self.s_a, self.s_b)
        reg = response.context_data['invoice'].registration
        self.assertEqual(RegistrationDiscount.objects.filter(registration=reg).count(), 1)

        combo.active = False
        combo.save()
        response = self.client.get(reverse('showRegSummary'))

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 0, places=2)
        self.assertItemTotals(response, self.s_b, [20])
        self.assertEqual(RegistrationDiscount.objects.filter(registration=reg).count(), 0)

    def test_discounts_reported_for_event_registrations(self):
        ''' Other apps can ask which discounts apply to a registration. '''
        combo = self.make_combo(percentDiscount=50)

        response = self.checkout(self.s_b)
        reg = response.context_data['invoice'].registration
        er = reg.eventregistration_set.get()

        report = reportDiscounts(sender=None, eventregistrations=[er.id])

        self.assertEqual(list(report.keys()), [er.id])
        self.assertEqual(len(report[er.id]), 1)
        self.assertEqual(report[er.id][0]['name'], combo.name)
        self.assertEqual(report[er.id][0]['type'], 'discount')
        self.assertAlmostEqual(report[er.id][0]['amount'], 10, places=2)

    def test_dollar_discount_larger_than_price(self):
        '''
        A discount of more than the price of everything in the cart makes
        everything free, and no item has a negative price.
        '''
        self.make_combo(
            discountType=DiscountCombo.DiscountType.dollarDiscount, dollarDiscount=50,
        )

        response = self.checkout(self.s_a, self.s_b)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 30, places=2)
        self.assertItemTotals(response, self.s_a, [0])
        self.assertItemTotals(response, self.s_b, [0])
        self.assertAlmostEqual(response.context_data['invoice'].total, 0, places=2)

    def test_dollar_discount_larger_than_matched_item(self):
        '''
        A $25 discount that is earned by the $20 item makes that item free,
        and the remaining $5 comes off of the other item.
        '''
        self.make_combo(
            discountType=DiscountCombo.DiscountType.dollarDiscount, dollarDiscount=25,
        )

        response = self.checkout(self.s_a, self.s_b)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 25, places=2)
        self.assertItemTotals(response, self.s_a, [5])
        self.assertItemTotals(response, self.s_b, [0])


class DiscountComboSaveTest(DiscountAllocationBase):

    def test_values_for_other_discount_types_are_not_saved(self):
        combo = self.make_combo(
            percentDiscount=50, dollarDiscount=5, onlinePrice=10, doorPrice=10,
        )
        combo.refresh_from_db()

        self.assertEqual(combo.percentDiscount, 50)
        self.assertIsNone(combo.dollarDiscount)
        self.assertIsNone(combo.onlinePrice)
        self.assertIsNone(combo.doorPrice)

        combo.discountType = DiscountCombo.DiscountType.dollarDiscount
        combo.dollarDiscount = 5
        combo.percentUniversallyApplied = True
        combo.save()
        combo.refresh_from_db()

        self.assertEqual(combo.dollarDiscount, 5)
        self.assertIsNone(combo.percentDiscount)
        self.assertFalse(combo.percentUniversallyApplied)
