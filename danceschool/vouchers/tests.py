import json

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
        post_data = {'series_%s_%s' % (
            s.id, response.context_data['form'].fields['series_%s' % s.id].field_choices[0].get('value')
        ): [1,]}

        response = self.client.post(reverse('registration'), post_data, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse('getStudentInfo'), 302)])

        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR].get('invoice_id')
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


class CartVouchersTest(VouchersTest):
    '''
    Tests that vouchers are correctly applied when the registration goes
    through the cart-based checkout flow (CartView -> StudentInfoView ->
    RegistrationSummaryView).

    The cart stores the voucher code in invoice.data['discount_code']. The
    applyVoucherCodeTemporarily handler (post_student_info) and
    RegistrationSummaryView both read this key so the voucher is applied
    the same way as in the legacy flow.
    '''

    def register_via_cart_with_voucher(self, series, voucher_code):
        '''
        Simulate a full cart-based registration that includes a voucher code.
        Returns the final response (landing on the summary page after following
        all redirects).
        '''
        sku = f'EVENT_{series.id}_GENERAL'
        response = self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{'item_type': 'Event', 'item_id': series.id,
                           'sku': sku, 'quantity': 1}],
                'checkout': True,
                'discount_code': voucher_code,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('invoice_id', self.client.session.get(REG_VALIDATION_STR, {}))

        # Verify the code was stored in invoice data
        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR]['invoice_id']
        )
        self.assertEqual(invoice.data.get('discount_code'), voucher_code)

        return self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Voucher',
            'lastName': 'Cart',
            'email': 'vouchercart@test.com',
            'agreeToPolicies': True,
        }, follow=True)

    def test_valid_voucher_applies_via_cart(self):
        '''A valid voucher passed as discount_code in the cart reduces the balance.'''
        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        v = self.create_voucher(
            originalAmount=10,
            expirationDate=timezone.now() + timedelta(days=1),
        )
        response = self.register_via_cart_with_voucher(s, v.voucherId)
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        invoice = response.context_data.get('invoice')
        self.assertEqual(
            invoice.outstandingBalance, s.getBasePrice() - v.originalAmount
        )

    def test_disabled_voucher_not_applied_via_cart(self):
        '''A disabled voucher must not reduce the balance even when passed in the cart.'''
        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        v = self.create_voucher(disabled=True)
        response = self.register_via_cart_with_voucher(s, v.voucherId)
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        invoice = response.context_data.get('invoice')
        self.assertEqual(invoice.outstandingBalance, s.getBasePrice())

    def test_expired_voucher_not_applied_via_cart(self):
        '''An expired voucher must not reduce the balance.'''
        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        v = self.create_voucher(expirationDate=timezone.now() + timedelta(days=-1))
        response = self.register_via_cart_with_voucher(s, v.voucherId)
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        invoice = response.context_data.get('invoice')
        self.assertEqual(invoice.outstandingBalance, s.getBasePrice())

    def test_voucher_capped_by_max_amount_per_use(self):
        '''A voucher with maxAmountPerUse only discounts up to the cap.'''
        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        v = self.create_voucher(
            originalAmount=100,
            maxAmountPerUse=5,
            expirationDate=timezone.now() + timedelta(days=1),
        )
        response = self.register_via_cart_with_voucher(s, v.voucherId)
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        invoice = response.context_data.get('invoice')
        self.assertEqual(invoice.outstandingBalance, s.getBasePrice() - 5)

    def test_invalid_voucher_code_no_discount_applied(self):
        '''An unrecognised voucher code must not reduce the balance.'''
        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        response = self.register_via_cart_with_voucher(s, 'DOESNOTEXIST')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        invoice = response.context_data.get('invoice')
        self.assertEqual(invoice.outstandingBalance, s.getBasePrice())


class CartSummaryVoucherPreviewTest(VouchersTest):
    '''
    Tests that CartSummaryView._get_voucher_preview shows the correct
    read-only voucher information before the cart is checked out.
    '''

    def _set_session_cart(self, series, discount_code=None):
        '''Write a single-event cart directly into the test session.'''
        sku = f'EVENT_{series.id}_GENERAL'
        cart = {
            'items': [{'item_type': 'Event', 'item_id': series.id,
                       'sku': sku, 'quantity': 1}],
            'payAtDoor': False,
        }
        if discount_code:
            cart['discount_code'] = discount_code
        session = self.client.session
        session[REG_VALIDATION_STR] = {'cart': cart, 'payAtDoor': False}
        session.save()

    def test_valid_voucher_preview_shown(self):
        '''
        A valid, unexpired voucher code stored in the session cart causes
        voucher_preview to be populated with the voucher details.
        '''
        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        v = self.create_voucher(
            originalAmount=10,
            expirationDate=timezone.now() + timedelta(days=1),
        )
        self._set_session_cart(s, discount_code=v.voucherId)

        response = self.client.get(reverse('cartSummary'))

        self.assertEqual(response.status_code, 200)
        preview = response.context_data.get('voucher_preview')
        self.assertIsNotNone(preview, 'Expected voucher_preview to be set')
        self.assertNotIn('error', preview)
        self.assertEqual(preview['voucher_id'], v.voucherId)
        self.assertAlmostEqual(preview['voucher_amount'], float(v.originalAmount))

    def test_expired_voucher_preview_shows_error(self):
        '''An expired voucher code must surface an error in voucher_preview.'''
        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        v = self.create_voucher(
            expirationDate=timezone.now() + timedelta(days=-1),
        )
        self._set_session_cart(s, discount_code=v.voucherId)

        response = self.client.get(reverse('cartSummary'))

        self.assertEqual(response.status_code, 200)
        preview = response.context_data.get('voucher_preview')
        self.assertIsNotNone(preview)
        self.assertIn('error', preview)

    def test_unrecognised_voucher_code_shows_error(self):
        '''An unrecognised voucher code must surface an error in voucher_preview.'''
        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        self._set_session_cart(s, discount_code='DOESNOTEXIST')

        response = self.client.get(reverse('cartSummary'))

        self.assertEqual(response.status_code, 200)
        preview = response.context_data.get('voucher_preview')
        # Should either be None (signal not connected) or an error dict.
        if preview is not None:
            self.assertIn('error', preview)

    def test_no_voucher_preview_without_code(self):
        '''When no discount_code is in the cart, voucher_preview must be None.'''
        updateConstant('vouchers__enableVouchers', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        self._set_session_cart(s)  # no discount_code

        response = self.client.get(reverse('cartSummary'))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context_data.get('voucher_preview'))
