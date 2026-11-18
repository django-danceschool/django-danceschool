from django.urls import reverse

from dynamic_preferences.registries import global_preferences_registry

from danceschool.core.constants import REG_VALIDATION_STR, updateConstant
from danceschool.core.models import Invoice
from danceschool.core.tests.test_tax import TaxTestMixin

from ..handlers import reportVouchers
from ..models import ClassVoucher, VoucherCredit
from .base import BaseVouchersTest


class VoucherBalanceTest(BaseVouchersTest):
    '''
    The amount that is left on a voucher is reduced when an invoice that it
    was used for is paid, and not before.
    '''

    def setUp(self):
        updateConstant('vouchers__enableVouchers', True)
        self.series = self.create_series(
            classDescription=self.levelOneClassDescription
        )
        self.other_series = self.create_series(
            classDescription=self.levelTwoClassDescription
        )
        self.price = self.series.getBasePrice()

    def test_amount_left_reflects_refunds_and_credits(self):
        voucher = self.create_voucher(originalAmount=10, maxAmountPerUse=8)
        self.assertEqual(voucher.amountLeft, 10)
        self.assertEqual(voucher.maxToUse, 8)

        voucher.refundAmount = 4
        voucher.save()
        self.assertEqual(voucher.amountLeft, 6)
        self.assertEqual(voucher.maxToUse, 6)

        VoucherCredit.objects.create(voucher=voucher, amount=3)
        self.assertEqual(voucher.amountLeft, 9)
        self.assertEqual(voucher.maxToUse, 8)

    def test_voucher_is_used_when_invoice_is_paid(self):
        voucher = self.create_voucher(originalAmount=100, maxAmountPerUse=30)

        response = self.checkout(self.series, code=voucher.voucherId)
        self.assertVoucherApplied(response, voucher, 30)

        # Nothing has been used yet, because the invoice has not been paid.
        self.assertFalse(voucher.voucheruse_set.get().applied)
        self.assertEqual(voucher.amountLeft, 100)
        self.assertEqual(self.get_invoice().outstandingBalance, self.price - 30)

        invoice = self.pay()

        self.assertEqual(invoice.status, Invoice.PaymentStatus.paid)
        self.assertTrue(voucher.voucheruse_set.get().applied)
        self.assertEqual(voucher.amountLeft, 70)

    def test_second_use_is_limited_to_amount_left(self):
        voucher = self.create_voucher(originalAmount=self.price + 10)

        # The voucher covers the entire price, so the registration is
        # finalized without any payment.
        response = self.checkout(self.series, code=voucher.voucherId)
        self.assertVoucherApplied(response, voucher, self.price)
        self.assertEqual(voucher.amountLeft, 10)

        self.new_session()
        response = self.checkout(self.other_series, code=voucher.voucherId)
        self.assertVoucherApplied(response, voucher, 10)
        self.assertEqual(self.get_invoice().outstandingBalance, self.price - 10)

    def test_voucher_is_applied_once_if_customer_information_is_resubmitted(self):
        '''
        Going back and submitting the customer information form again does
        not apply the voucher to the invoice a second time.
        '''
        voucher = self.create_voucher(originalAmount=100, maxAmountPerUse=10)

        response = self.checkout(self.series, code=voucher.voucherId)
        self.assertVoucherApplied(response, voucher, 10)

        response = self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Voucher', 'lastName': 'Customer',
            'email': 'test@customer.com', 'agreeToPolicies': True,
        }, follow=True)

        self.assertVoucherApplied(response, voucher, 10)
        invoice = self.get_invoice()
        self.assertAlmostEqual(invoice.total, self.price - 10, places=2)

    def test_staff_credit_is_kept_when_summary_is_reloaded(self):
        '''
        A post-tax voucher is applied to the item's adjustments, and so is a
        credit entered by staff before the invoice is paid.  On a reload of
        the summary page, the voucher is applied again and the credit is kept.
        '''
        voucher = self.create_voucher(originalAmount=5)
        voucher.beforeTax = False
        voucher.save()

        response = self.checkout(self.series, code=voucher.voucherId)
        self.assertVoucherApplied(response, voucher, 5)

        # Staff add a $3 credit, as they would in the admin.
        item = self.get_invoice().invoiceitem_set.get()
        self.assertEqual(item.adjustments, -5)
        item.adjustments = -8
        item.save()

        response = self.client.get(reverse('showRegSummary'))
        self.assertEqual(response.status_code, 200)
        uses = self.get_invoice().voucheruse_set.filter(voucher=voucher)
        self.assertEqual(uses.get().amount, 5)
        invoice = self.get_invoice()
        self.assertEqual(invoice.invoiceitem_set.get().adjustments, -8)
        self.assertAlmostEqual(invoice.outstandingBalance, self.price - 8, places=2)

    def test_only_latest_voucher_code_is_applied(self):
        '''
        If the customer information form is submitted again with a different
        voucher code, then only the new voucher is applied.
        '''
        first = self.create_voucher(originalAmount=100, maxAmountPerUse=10)
        second = self.create_voucher(
            voucherId='SECOND_VOUCHER', name='Second Voucher',
            originalAmount=100, maxAmountPerUse=4,
        )

        response = self.checkout(self.series, gift=first.voucherId)
        self.assertVoucherApplied(response, first, 10)

        response = self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Voucher', 'lastName': 'Customer',
            'email': 'test@customer.com', 'agreeToPolicies': True,
            'gift': second.voucherId,
        }, follow=True)

        self.assertVoucherApplied(response, second, 4)
        invoice = self.get_invoice()
        self.assertFalse(invoice.voucheruse_set.filter(voucher=first).exists())
        self.assertAlmostEqual(invoice.total, self.price - 4, places=2)

    def test_vouchers_reported_for_event_registrations(self):
        ''' Other apps can ask which vouchers apply to a registration. '''
        voucher = self.create_voucher(originalAmount=100, maxAmountPerUse=10)
        self.checkout(self.series, code=voucher.voucherId)
        er = self.get_invoice().registration.eventregistration_set.get()

        report = reportVouchers(sender=None, eventregistrations=[er.id])

        self.assertEqual(list(report.keys()), [er.id])
        self.assertEqual(len(report[er.id]), 1)
        self.assertEqual(report[er.id][0]['type'], 'voucher')
        self.assertEqual(
            report[er.id][0]['name'], '%s: %s' % (voucher.voucherId, voucher.name)
        )
        self.assertAlmostEqual(report[er.id][0]['amount'], 10, places=2)


class VoucherTaxTest(TaxTestMixin, BaseVouchersTest):
    '''
    A voucher is applied either before or after tax. The series is taxed at
    10%, and the voucher is for $10.
    '''

    def setUp(self):
        updateConstant('vouchers__enableVouchers', True)
        self.gp = global_preferences_registry.manager()
        self.setUpTax()
        self.series = self.create_series()
        self.price = self.series.getBasePrice()

    def tearDown(self):
        self.gp['registration__buyerPaysSalesTax'] = True
        self.tearDownTax()

    def use_voucher(self, beforeTax, buyerPays=True):
        self.gp['registration__buyerPaysSalesTax'] = buyerPays
        voucher = self.create_voucher(originalAmount=10)
        voucher.beforeTax = beforeTax
        voucher.save()
        response = self.checkout(self.series, code=voucher.voucherId)
        self.assertVoucherApplied(response, voucher, 10)
        return self.get_invoice()

    def test_voucher_before_tax(self):
        ''' Tax is charged on the price after the voucher. '''
        invoice = self.use_voucher(beforeTax=True)

        self.assertAlmostEqual(invoice.total, self.price - 10, places=4)
        self.assertAlmostEqual(invoice.taxes, (self.price - 10) * 0.1, places=4)
        self.assertAlmostEqual(invoice.adjustments, 0, places=4)
        self.assertAlmostEqual(
            invoice.outstandingBalance, (self.price - 10) * 1.1, places=2
        )

    def test_voucher_after_tax(self):
        ''' Tax is charged on the full price, and the voucher comes off after. '''
        invoice = self.use_voucher(beforeTax=False)

        self.assertAlmostEqual(invoice.total, self.price, places=4)
        self.assertAlmostEqual(invoice.taxes, self.price * 0.1, places=4)
        self.assertAlmostEqual(invoice.adjustments, -10, places=4)
        self.assertAlmostEqual(
            invoice.outstandingBalance, (self.price * 1.1) - 10, places=2
        )

    def test_voucher_after_tax_when_seller_pays_tax(self):
        ''' The price includes the tax, so the balance is the price less $10. '''
        invoice = self.use_voucher(beforeTax=False, buyerPays=False)

        self.assertAlmostEqual(invoice.total, self.price, places=4)
        self.assertAlmostEqual(invoice.adjustments, -10, places=4)
        self.assertAlmostEqual(invoice.outstandingBalance, self.price - 10, places=2)

    def test_voucher_before_tax_when_seller_pays_tax(self):
        invoice = self.use_voucher(beforeTax=True, buyerPays=False)

        self.assertAlmostEqual(invoice.total, self.price - 10, places=4)
        self.assertAlmostEqual(
            invoice.taxes, (self.price - 10) * 0.1 / 1.1, places=4
        )
        self.assertAlmostEqual(invoice.outstandingBalance, self.price - 10, places=2)


class VoucherLinkTest(BaseVouchersTest):
    '''
    A voucher code can be passed in a link to the registration page, and it
    is then used as the discount code of the cart.
    '''

    def setUp(self):
        updateConstant('vouchers__enableVouchers', True)
        self.voucher = self.create_voucher(originalAmount=10)

    def cart_code(self):
        return self.client.session.get(REG_VALIDATION_STR, {}).get(
            'cart', {}
        ).get('discount_code')

    def test_valid_code_in_link_is_kept(self):
        response = self.client.get(
            reverse('registration') + '?referral=' + self.voucher.voucherId
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.cart_code(), self.voucher.voucherId)

    def test_invalid_code_in_link_is_not_kept(self):
        response = self.client.get(reverse('registration') + '?referral=NOT_A_CODE')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.cart_code())
        self.assertTrue(list(response.context['messages']))

    def test_restricted_voucher_in_link_is_kept(self):
        '''
        A voucher that can only be used for a specific class can be passed in
        a link, before anything is in the cart.
        '''
        series = self.create_series()
        ClassVoucher.objects.create(
            classDescription=series.classDescription, voucher=self.voucher
        )
        self.client.get(reverse('registration') + '?referral=' + self.voucher.voucherId)
        self.assertEqual(self.cart_code(), self.voucher.voucherId)

    def test_disabled_voucher_in_link_is_not_kept(self):
        self.voucher.disabled = True
        self.voucher.save()
        self.client.get(reverse('registration') + '?referral=' + self.voucher.voucherId)
        self.assertIsNone(self.cart_code())
