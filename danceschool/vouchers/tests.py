from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from danceschool.core.constants import REG_VALIDATION_STR, updateConstant
from danceschool.core.utils.tests import DefaultSchoolTestCase
from danceschool.core.models import Registration, Invoice

from .models import Voucher


class VouchersTest(DefaultSchoolTestCase):

    def create_voucher(self, **kwargs):

        v = Voucher(
            voucherId=kwargs.get('voucherId', 'TEST_VOUCHER'),
            name=kwargs.get('name', 'Test Voucher'),
            originalAmount=kwargs.get('originalAmount', 10),
            maxAmountPerUse=kwargs.get('maxAmountPerUse', None),
            disabled=kwargs.get('disabled', False),
            expirationDate=kwargs.get('expirationDate', None),
            forPreviousCustomersOnly=kwargs.get('forPreviousCustomersOnly', False),
            forFirstTimeCustomersOnly=kwargs.get('forFirstTimeCustomersOnly', False)
        )
        v.save()
        return v

    def register_to_check_voucher(self, voucherCode, series):
        '''
        This method makes it easy to determine whether discounts are working
        correctly for a single class registration
        '''
        s = series

        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(s, response.context_data['regOpenSeries'])

        # Sign up for the series, and check that we proceed to the student information page.
        # Because of the way that roles are encoded on this form, we just grab the value to pass
        # from the form itself.
        post_data = {'series_%s' % s.id: response.context_data['form'].fields['series_%s' % s.id].choices[0][0]}

        response = self.client.post(reverse('registration'), post_data, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse('getStudentInfo'), 302)])

        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR].get('invoiceId')
        )
        tr = Registration.objects.filter(invoice=invoice).first()
        self.assertTrue(tr.eventregistration_set.filter(event__id=s.id).exists())
        self.assertFalse(tr.final)
        self.assertEqual(tr.payAtDoor, False)

        # Check that the student info page lists the correct item amounts and subtotal
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(response.context_data.get('invoice').total, s.getBasePrice())

        # Continue to the summary page
        post_data = {
            'firstName': 'Voucher',
            'lastName': 'Customer',
            'email': 'test@customer.com',
            'agreeToPolicies': True,
            'gift': voucherCode,
        }
        return self.client.post(reverse('getStudentInfo'), post_data, follow=True)

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
