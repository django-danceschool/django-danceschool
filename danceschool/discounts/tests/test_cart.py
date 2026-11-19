import json

from django.urls import reverse

from danceschool.core.constants import REG_VALIDATION_STR, updateConstant

from ..models import DiscountCombo
from .base import BaseDiscountsTest


class CartDiscountsTest(BaseDiscountsTest):
    '''
    Tests that discounts are correctly applied when the registration goes
    through the cart-based checkout flow (CartView -> StudentInfoView ->
    RegistrationSummaryView).
    '''

    def register_via_cart(self, series, payAtDoor=False, discount_code=None):
        '''
        Simulate a full cart-based registration for a single series, stopping
        just before the summary page. Returns the response from the student
        info submission (with follow=True so it lands on the summary page).
        '''
        sku = f'EVENT_{series.id}_GENERAL'
        cart_data = {
            'items': [{'item_type': 'Event', 'item_id': series.id,
                       'sku': sku, 'quantity': 1}],
            'checkout': True,
        }
        if payAtDoor:
            cart_data['payAtDoor'] = True
            self.client.force_login(self.superuser)
        if discount_code:
            cart_data['discount_code'] = discount_code

        response = self.client.post(
            reverse('cart'),
            data=json.dumps(cart_data),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('invoice_id', self.client.session.get(REG_VALIDATION_STR, {}))

        return self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Cart',
            'lastName': 'Discounter',
            'email': 'cart@discount.com',
            'agreeToPolicies': True,
        }, follow=True)

    def test_automatic_discount_applies_via_cart(self):
        '''
        An automatic discount (no voucher code required) should apply when
        the registration is created through the cart checkout flow.
        '''
        updateConstant('general__discountsEnabled', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        combo, _ = self.create_discount()

        response = self.register_via_cart(s)
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        invoice = response.context_data.get('invoice')
        expected_price = self.defaultPricing.onlinePrice - 5  # flatPrice combo
        self.assertEqual(invoice.outstandingBalance, expected_price)
        self.assertGreater(response.context_data.get('total_discount_amount', 0), 0)

    def test_inactive_discount_not_applied_via_cart(self):
        '''An inactive discount must not be applied in the cart flow.'''
        updateConstant('general__discountsEnabled', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        self.create_discount(active=False)

        response = self.register_via_cart(s)
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        invoice = response.context_data.get('invoice')
        self.assertEqual(invoice.outstandingBalance, s.getBasePrice())
        self.assertEqual(response.context_data.get('total_discount_amount', 0), 0)

    def test_voucher_code_discount_applies_via_cart(self):
        '''
        A discount gated behind a voucher code should apply when the code is
        passed as discount_code in the cart payload.
        '''
        updateConstant('general__discountsEnabled', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        combo, _ = self.create_discount(voucherId='CARTCODE')

        response = self.register_via_cart(s, discount_code='CARTCODE')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        invoice = response.context_data.get('invoice')
        expected_price = self.defaultPricing.onlinePrice - 5
        self.assertEqual(invoice.outstandingBalance, expected_price)

    def test_wrong_voucher_code_discount_not_applied_via_cart(self):
        '''An incorrect voucher code must not unlock a code-gated discount.'''
        updateConstant('general__discountsEnabled', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        self.create_discount(voucherId='REALCODE')

        response = self.register_via_cart(s, discount_code='WRONGCODE')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        invoice = response.context_data.get('invoice')
        self.assertEqual(invoice.outstandingBalance, s.getBasePrice())


class CartSummaryDiscountPreviewTest(BaseDiscountsTest):
    '''
    Tests that CartSummaryView._get_discount_preview shows the correct
    read-only discount information before the cart is checked out.
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

    def test_discount_preview_shown_for_matching_discount(self):
        '''
        When an active discount applies to the items in the cart,
        discount_preview in the context must contain the expected savings.
        '''
        updateConstant('general__discountsEnabled', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        # Default create_discount() creates a flatPrice combo that reduces the
        # online price by $5 for a single class (see BaseDiscountsTest).
        combo, _ = self.create_discount(
            discountType=DiscountCombo.DiscountType.dollarDiscount,
            dollarDiscount=10,
        )
        self._set_session_cart(s)

        response = self.client.get(reverse('cartSummary'))

        self.assertEqual(response.status_code, 200)
        preview = response.context_data.get('discount_preview')
        self.assertIsNotNone(preview, 'Expected discount_preview to be set')
        self.assertGreater(preview['total_discount'], 0)
        discount_names = [d['name'] for d in preview['discounts']]
        self.assertIn(combo.name, discount_names)

    def test_no_discount_preview_when_discounts_disabled(self):
        '''
        When the discounts feature is disabled, discount_preview must be None.
        '''
        updateConstant('general__discountsEnabled', False)
        s = self.create_series(pricingTier=self.defaultPricing)
        self.create_discount()
        self._set_session_cart(s)

        response = self.client.get(reverse('cartSummary'))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context_data.get('discount_preview'))

    def test_no_discount_preview_without_matching_discount(self):
        '''
        When no discount is configured, discount_preview must be None.
        '''
        updateConstant('general__discountsEnabled', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        # No discount created.
        self._set_session_cart(s)

        response = self.client.get(reverse('cartSummary'))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context_data.get('discount_preview'))

    def test_voucher_code_gated_discount_preview(self):
        '''
        A discount requiring a voucher code only appears in the preview when
        the correct code is present in the cart.
        '''
        updateConstant('general__discountsEnabled', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        combo, _ = self.create_discount(voucherId='SUMMARYCODE')

        # Without the code: no preview.
        self._set_session_cart(s)
        response = self.client.get(reverse('cartSummary'))
        self.assertIsNone(response.context_data.get('discount_preview'))

        # With the correct code: preview shows the discount.
        self._set_session_cart(s, discount_code='SUMMARYCODE')
        response = self.client.get(reverse('cartSummary'))
        preview = response.context_data.get('discount_preview')
        self.assertIsNotNone(preview)
        self.assertGreater(preview['total_discount'], 0)
