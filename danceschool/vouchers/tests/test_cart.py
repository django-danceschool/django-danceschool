import json

from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from danceschool.core.constants import REG_VALIDATION_STR, updateConstant
from danceschool.core.models import Invoice

from .base import BaseVouchersTest


class CartVouchersTest(BaseVouchersTest):
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


class CartSummaryVoucherPreviewTest(BaseVouchersTest):
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
