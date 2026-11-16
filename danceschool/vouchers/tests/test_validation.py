from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from danceschool.core.constants import updateConstant
from danceschool.core.models import Invoice

from .base import BaseVouchersTest


class VouchersTest(BaseVouchersTest):

    def test_nonexistent_voucher(self):
        ''' Check that entering a non-existent voucher fails '''

        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_voucher('MADEUP_CODE', s)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.redirect_chain)
        self.assertTrue(response.context_data['form'].errors.get('gift'))

    def test_disabled_voucher(self):
        ''' Create a disabled voucher and ensure that it fails '''

        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        v = self.create_voucher(disabled=True)

        response = self.register_to_check_voucher(v.voucherId, s)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.redirect_chain)
        self.assertTrue(response.context_data['form'].errors.get('gift'))

    def test_expired_voucher(self):
        '''
        Create a voucher that has an expiration date of yesterday
        and ensure that it fails
        '''

        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        v = self.create_voucher(expirationDate=timezone.now() + timedelta(days=-1))

        response = self.register_to_check_voucher(v.voucherId, s)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.redirect_chain)
        self.assertTrue(response.context_data['form'].errors.get('gift'))

    def test_existing_customers_voucher(self):
        '''
        Create a voucher for existing customers only and ensure
        that it fails for an anonymous new customer
        '''

        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        v = self.create_voucher(
            forPreviousCustomersOnly=True,
            expirationDate=timezone.now() + timedelta(days=1),
        )

        response = self.register_to_check_voucher(v.voucherId, s)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.redirect_chain)
        self.assertTrue(response.context_data['form'].errors.get('gift'))

    def test_vouchers_disabled(self):
        '''
        Disable vouchers and ensure that the voucher fails
        '''

        updateConstant('vouchers__enableVouchers', False)
        s = self.create_series(pricingTier=self.defaultPricing)
        v = self.create_voucher(
            expirationDate=timezone.now() + timedelta(days=1),
        )

        response = self.register_to_check_voucher(v.voucherId, s)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.redirect_chain)
        self.assertTrue(response.context_data['form'].errors.get('gift'))

    def test_maxamountperuse(self):
        '''
        Ensure that a voucher with a max amount per use succeeds, but
        only subtracts the max amount per use.
        '''

        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        v = self.create_voucher(
            expirationDate=timezone.now() + timedelta(days=1),
            maxAmountPerUse=2,
        )

        response = self.register_to_check_voucher(v.voucherId, s)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal - v.maxAmountPerUse
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('vouchers',{}).get('total_pretax'), v.maxAmountPerUse)
        self.assertIn(v.name, [x.get('name') for x in response.context_data.get('vouchers', {}).get('items', [])])

        tvu = v.voucheruse_set.filter(invoice=invoice)
        self.assertTrue(tvu.exists() and tvu.count() == 1)
        self.assertFalse(tvu.first().applied)
        self.assertEqual(tvu.first().amount, v.maxAmountPerUse)

    def test_fullamountused(self):
        '''
        Remove the max amount per use restriction and ensure that the
        voucher is applied for the full $10
        '''
        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        v = self.create_voucher()

        response = self.register_to_check_voucher(v.voucherId, s)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal - v.originalAmount
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('vouchers',{}).get('total_pretax'), v.originalAmount)
        self.assertIn(v.name, [x.get('name') for x in response.context_data.get('vouchers', {}).get('items', [])])

        tvu = v.voucheruse_set.filter(invoice=invoice)
        self.assertTrue(tvu.exists() and tvu.count() == 1)
        self.assertFalse(tvu.first().applied)
        self.assertEqual(tvu.first().amount, v.originalAmount)

    def test_vouchermakesitfree(self):
        '''
        Make a voucher larger than the price of the registration
        and ensure that this makes the registration free (and that
        it gets processed as such)
        '''
        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        v = self.create_voucher(
            originalAmount=self.defaultPricing.getBasePrice() + 10,
            maxAmountPerUse=None,
        )

        response = self.register_to_check_voucher(v.voucherId, s)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(invoice.total, 0)
        self.assertEqual(response.context_data.get('zero_balance'), True)
        self.assertEqual(response.context_data.get('vouchers',{}).get('total_pretax'), s.getBasePrice())
        self.assertIn(v.name, [x.get('name') for x in response.context_data.get('vouchers', {}).get('items', [])])

        reg = response.context_data.get('registration')
        tvu = v.voucheruse_set.filter(invoice=invoice)
        self.assertTrue(tvu.exists() and tvu.count() == 1)
        self.assertTrue(tvu.first().applied)
        self.assertEqual(tvu.first().amount, s.getBasePrice())
        self.assertTrue(reg)
        self.assertTrue(reg.final)
        self.assertEqual(reg.invoice, invoice)
        self.assertTrue(invoice.status == Invoice.PaymentStatus.paid)
        self.assertEqual(invoice.outstandingBalance, 0)
