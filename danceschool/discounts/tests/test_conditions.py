from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from danceschool.core.constants import updateConstant

from .base import BaseDiscountsTest


class DiscountsConditionsTest(BaseDiscountsTest):

    def test_inactive_discount(self):
        '''
        Make a discount inactive and make sure that it doesn't work
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(active=False)
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s, s.getBasePrice())
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 0)
        self.assertFalse(response.context_data.get('addonItems'))
        self.assertFalse(response.context_data.get('discount_codes'))

    def test_expired_discount(self):
        '''
        Create an expired discount and make sure that it doesn't work.
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(
            expirationDate=timezone.now() + timedelta(days=-1)
        )
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s, s.getBasePrice())
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 0)
        self.assertFalse(response.context_data.get('addonItems'))
        self.assertFalse(response.context_data.get('discount_codes'))

    def test_discounts_disabled(self):
        ''' Disable discounts and check that they don't work anymore '''

        updateConstant('general__discountsEnabled', False)
        test_combo, test_component = self.create_discount()
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s, s.getBasePrice())
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 0)
        self.assertFalse(response.context_data.get('addonItems'))
        self.assertFalse(response.context_data.get('discount_codes'))

    def test_notenoughpoints(self):
        '''
        Set the discount's components so that this discount is too small to apply, and
        check that it doesn't get applied.
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(quantity=10)
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s, s.getBasePrice())
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 0)
        self.assertFalse(response.context_data.get('addonItems'))
        self.assertFalse(response.context_data.get('discount_codes'))

    def test_noearlybird(self):
        '''
        Create an early registration discount that requires three day
        advance registration and ensure that it does not work less than
        three days in advance.
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(daysInAdvanceRequired=3)
        s = self.create_series(
            pricingTier=self.defaultPricing,
            startTime=timezone.now() + timedelta(days=1)
        )

        response = self.register_to_check_discount(s, s.getBasePrice())
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 0)
        self.assertFalse(response.context_data.get('addonItems'))
        self.assertFalse(response.context_data.get('discount_codes'))

    def test_preregonly(self):
        '''
        Create a discount that only can be used for pre-registration and ensure
        that it does not work at the door.
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(availableAtDoor=False)
        s = self.create_series(
            pricingTier=self.defaultPricing,
            startTime=timezone.now() + timedelta(days=1)
        )

        self.client.login(username=self.superuser.username, password='pass')
        response = self.register_to_check_discount(s, s.getBasePrice(payAtDoor=True), True)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice(payAtDoor=True))
        self.assertEqual(
            invoice.total, invoice.grossTotal
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 0)
        self.assertFalse(response.context_data.get('addonItems'))
        self.assertFalse(response.context_data.get('discount_codes'))

    def test_dooronly(self):
        '''
        Create a discount that only can be used at the door and ensure
        that it does not work in advance.
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(availableOnline=False)
        s = self.create_series(
            pricingTier=self.defaultPricing,
            startTime=timezone.now() + timedelta(days=1)
        )

        response = self.register_to_check_discount(s, s.getBasePrice(), False)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 0)
        self.assertFalse(response.context_data.get('addonItems'))
        self.assertFalse(response.context_data.get('discount_codes'))

    def test_voucher_required(self):
        '''
        Create a discount that uses a voucher code and ensure that it doesn't
        work if the voucher code is not specified.
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(voucherId='ABC123')
        s = self.create_series(
            pricingTier=self.defaultPricing,
            startTime=timezone.now() + timedelta(days=1)
        )

        response = self.register_to_check_discount(s, s.getBasePrice(), False)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 0)
        self.assertFalse(response.context_data.get('addonItems'))
        self.assertFalse(response.context_data.get('discount_codes'))

    def test_voucher_code_for_discount_that_does_not_apply(self):
        '''
        Entering the voucher code of a discount that does not apply to the
        items being registered for is an error on the voucher code field.
        '''
        updateConstant('general__discountsEnabled', True)
        # The discount needs more points than one registration provides.
        self.create_discount(voucherId='ABC123', quantity=10)
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s, voucherId='ABC123')

        self.assertFalse(response.redirect_chain)
        self.assertTrue(response.context_data['form'].errors.get('gift'))

    def test_flat_price_at_the_door(self):
        '''
        A flat price discount has a separate price for registration at the
        door, which is used for registrations at the door.
        '''
        updateConstant('general__discountsEnabled', True)
        self.create_discount(onlinePrice=30, doorPrice=45)
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s, payAtDoor=True)
        invoice = response.context_data.get('invoice')

        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, self.defaultPricing.doorPrice)
        self.assertEqual(invoice.total, 45)
        self.assertEqual(
            response.context_data.get('total_discount_amount'),
            self.defaultPricing.doorPrice - 45
        )
