from unittest import skipUnless

from django.apps import apps
from django.urls import reverse

from danceschool.core.constants import updateConstant
from danceschool.core.tests.test_tax import TaxTestMixin
from danceschool.core.models import Invoice

from .base import DiscountAllocationBase


@skipUnless(
    apps.is_installed('danceschool.vouchers'), 'The vouchers app is not installed.'
)
class DiscountWithVoucherTest(TaxTestMixin, DiscountAllocationBase):
    '''
    A voucher is applied to whatever remains after discounts. Here, series A
    ($10) earns no discount and series B ($20) is 100% off, so only series A
    has any remaining price for a voucher to be applied to. Both series are
    taxed at 10%, which the buyer pays.
    '''

    def setUp(self):
        super().setUp()
        self.setUpTax()
        self.gp['registration__buyerPaysSalesTax'] = True
        updateConstant('vouchers__enableVouchers', True)

        self.s_a = self.create_series(pricingTier=self.tier_a)
        self.s_b = self.create_series(pricingTier=self.tier_b)
        self.make_combo(percentDiscount=100)

    def tearDown(self):
        super().tearDown()
        self.tearDownTax()

    def make_voucher(self, amount, beforeTax):
        from danceschool.vouchers.models import Voucher
        return Voucher.objects.create(
            voucherId='ALLOCATION_TEST', name='Allocation Test Voucher',
            originalAmount=amount, beforeTax=beforeTax,
        )

    def get_invoice(self, response):
        return Invoice.objects.get(id=response.context_data['invoice'].id)

    def test_pretax_voucher_applies_to_remaining_price(self):
        voucher = self.make_voucher(5, beforeTax=True)
        response = self.checkout(self.s_a, self.s_b, discount_code=voucher.voucherId)
        invoice = self.get_invoice(response)

        self.assertEqual(invoice.voucheruse_set.get().amount, 5)
        self.assertAlmostEqual(invoice.total, 5, places=4)
        self.assertAlmostEqual(invoice.taxes, 0.5, places=4)
        self.assertAlmostEqual(invoice.outstandingBalance, 5.5, places=4)
        self.assertItemTotals(response, self.s_a, [5])
        self.assertItemTotals(response, self.s_b, [0])

    def test_posttax_voucher_is_limited_to_amount_owed(self):
        '''
        A gift certificate worth more than the amount owed is only drawn down
        by the amount owed ($10 plus 10% tax), and the discount remains.
        '''
        voucher = self.make_voucher(100, beforeTax=False)
        response = self.checkout(self.s_a, self.s_b, discount_code=voucher.voucherId)
        invoice = self.get_invoice(response)

        self.assertAlmostEqual(invoice.voucheruse_set.get().amount, 11, places=4)
        self.assertAlmostEqual(invoice.adjustments, -11, places=4)
        self.assertAlmostEqual(invoice.taxes, 1.0, places=4)
        self.assertAlmostEqual(invoice.outstandingBalance, 0, places=4)
        self.assertItemTotals(response, self.s_a, [10])
        self.assertItemTotals(response, self.s_b, [0])

    def test_posttax_voucher_when_seller_pays_tax(self):
        '''
        When the seller pays sales tax, the price includes the tax, so the
        amount owed is $10 and no tax is added to it.
        '''
        self.gp['registration__buyerPaysSalesTax'] = False
        voucher = self.make_voucher(100, beforeTax=False)
        response = self.checkout(self.s_a, self.s_b, discount_code=voucher.voucherId)
        invoice = self.get_invoice(response)

        self.assertAlmostEqual(invoice.voucheruse_set.get().amount, 10, places=4)
        self.assertAlmostEqual(invoice.adjustments, -10, places=4)
        self.assertAlmostEqual(invoice.outstandingBalance, 0, places=4)
        self.assertItemTotals(response, self.s_a, [10])
        self.assertItemTotals(response, self.s_b, [0])

    def test_pretax_and_posttax_vouchers_together(self):
        '''
        A pre-tax voucher reduces the tax, so a post-tax voucher on the same
        invoice is limited to what is owed after that: $10 less the $4 pre-tax
        voucher is $6, plus 10% tax, is $6.60.
        '''
        from danceschool.vouchers.models import Voucher, VoucherUse

        voucher = self.make_voucher(4, beforeTax=True)
        response = self.checkout(self.s_a, self.s_b, discount_code=voucher.voucherId)
        invoice = self.get_invoice(response)

        # Registration only accepts one voucher code, so the second voucher is
        # attached to the invoice directly, and the summary page is reloaded.
        gift = Voucher.objects.create(
            voucherId='ALLOCATION_GIFT', name='Allocation Test Gift Certificate',
            originalAmount=100, beforeTax=False,
        )
        VoucherUse.objects.create(
            voucher=gift, invoice=invoice, amount=0, beforeTax=False,
        )
        response = self.client.get(reverse('showRegSummary'))
        invoice = self.get_invoice(response)

        self.assertAlmostEqual(invoice.total, 6, places=4)
        self.assertAlmostEqual(invoice.taxes, 0.6, places=4)
        self.assertAlmostEqual(
            invoice.voucheruse_set.get(voucher=voucher).amount, 4, places=4
        )
        self.assertAlmostEqual(
            invoice.voucheruse_set.get(voucher=gift).amount, 6.6, places=4
        )
        self.assertAlmostEqual(invoice.adjustments, -6.6, places=4)
        self.assertAlmostEqual(invoice.outstandingBalance, 0, places=4)
        self.assertItemTotals(response, self.s_a, [6])
        self.assertItemTotals(response, self.s_b, [0])

    def test_reload_with_voucher_gives_same_totals(self):
        voucher = self.make_voucher(8, beforeTax=True)

        def check(response):
            invoice = self.get_invoice(response)
            self.assertAlmostEqual(invoice.total, 2, places=4)
            self.assertAlmostEqual(invoice.outstandingBalance, 2.2, places=4)
            self.assertEqual(invoice.voucheruse_set.get().amount, 8)
            self.assertItemTotals(response, self.s_a, [2])
            self.assertItemTotals(response, self.s_b, [0])

        check(self.checkout(self.s_a, self.s_b, discount_code=voucher.voucherId))
        check(self.client.get(reverse('showRegSummary')))
