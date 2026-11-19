from unittest import skipUnless

from django.apps import apps
from django.core.exceptions import ValidationError
from django.urls import reverse

from danceschool.core.constants import REG_VALIDATION_STR, updateConstant
from danceschool.core.tests.test_tax import TaxTestMixin
from danceschool.core.models import Invoice

from ..models import DiscountCombo
from .base import BaseDiscountsTest, DiscountAllocationBase


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


@skipUnless(
    apps.is_installed('danceschool.vouchers'), 'The vouchers app is not installed.'
)
class DoubleSubtractionWhenCodeInBothTablesTest(BaseDiscountsTest):
    '''
    Reproduces a bug where a code registered in BOTH DiscountCombo
    (with voucherId set) AND the Voucher table causes the CartSummaryView
    to subtract the discount AND the voucher amount from the user-facing
    net total, double-counting the price reduction.

    CartSummaryView.get_context_data (cart.py:758-761) subtracts the
    discount_preview total and the voucher_preview amount independently,
    with no guard for the case where the same code matched both systems.
    '''

    def test_shared_code_not_double_subtracted(self):
        from danceschool.vouchers.models import Voucher

        updateConstant('general__discountsEnabled', True)
        updateConstant('vouchers__enableVouchers', True)

        s = self.create_series(pricingTier=self.defaultPricing)
        gross = s.getBasePrice()

        # Same code in both tables.
        self.create_discount(
            voucherId='DBLCODE',
            discountType=DiscountCombo.DiscountType.dollarDiscount,
            dollarDiscount=10,
        )
        Voucher.objects.create(
            voucherId='DBLCODE',
            name='Shared Code Voucher',
            originalAmount=5,
            disabled=False,
        )

        # Set up cart with the shared code and view the summary.
        sku = f'EVENT_{s.id}_GENERAL'
        cart = {
            'items': [{'item_type': 'Event', 'item_id': s.id,
                       'sku': sku, 'quantity': 1}],
            'payAtDoor': False,
            'discount_code': 'DBLCODE',
        }
        session = self.client.session
        session[REG_VALIDATION_STR] = {'cart': cart, 'payAtDoor': False}
        session.save()

        response = self.client.get(reverse('cartSummary'))
        self.assertEqual(response.status_code, 200)
        net_total = response.context_data.get('net_total')

        # Whatever the correct resolution (apply only the discount, only
        # the voucher, or treat as ambiguous), it must NOT be both.
        # Current buggy behavior: gross - 10 - 5 = gross - 15.
        # Acceptable: net_total >= gross - max(10, 5) = gross - 10.
        self.assertGreaterEqual(
            net_total, gross - 10,
            msg=(
                'Code present in both DiscountCombo (voucherId) and '
                'Voucher tables produced over-discounted net_total {0} '
                '(gross {1}); expected at least {2}.'
            ).format(net_total, gross, gross - 10),
        )

    def make_shared_code(self):
        '''
        Codes saved before the admin refused shared codes may still be shared,
        so the voucher is created without checking it.
        '''
        from danceschool.vouchers.models import Voucher

        updateConstant('general__discountsEnabled', True)
        updateConstant('vouchers__enableVouchers', True)
        self.create_discount(
            voucherId='DBLCODE',
            discountType=DiscountCombo.DiscountType.dollarDiscount,
            dollarDiscount=10,
        )
        Voucher.objects.create(
            voucherId='DBLCODE', name='Shared Code Voucher', originalAmount=5,
        )

    def test_shared_code_is_a_discount_at_checkout(self):
        ''' Only the discount is applied, and no use of the voucher is recorded. '''
        self.make_shared_code()
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s, voucherId='DBLCODE')
        self.assertEqual(response.redirect_chain[-1][0], reverse('showRegSummary'))
        invoice = Invoice.objects.get(id=response.context_data['invoice'].id)

        self.assertEqual(invoice.outstandingBalance, s.getBasePrice() - 10)
        self.assertFalse(invoice.voucheruse_set.exists())
        self.assertFalse(response.context_data.get('voucher'))

    def test_admin_refuses_shared_code(self):
        from danceschool.vouchers.models import Voucher

        discount, _ = self.create_discount(
            voucherId='DISCOUNTCODE',
            discountType=DiscountCombo.DiscountType.dollarDiscount,
            dollarDiscount=10,
        )
        with self.assertRaises(ValidationError) as cm:
            Voucher(voucherId='DISCOUNTCODE', name='Voucher', originalAmount=5).clean()
        self.assertIn('voucherId', cm.exception.message_dict)

        Voucher.objects.create(voucherId='VOUCHERCODE', name='Voucher', originalAmount=5)
        discount.voucherId = 'VOUCHERCODE'
        with self.assertRaises(ValidationError) as cm:
            discount.clean()
        self.assertIn('voucherId', cm.exception.message_dict)

        # Codes that are not shared are allowed.
        Voucher(voucherId='OTHERCODE', name='Voucher', originalAmount=5).clean()
        discount.voucherId = 'OTHERDISCOUNT'
        discount.clean()
