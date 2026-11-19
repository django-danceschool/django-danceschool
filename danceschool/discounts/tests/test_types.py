from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from danceschool.core.constants import updateConstant
from danceschool.core.models import Invoice

from ..models import DiscountCombo
from .base import BaseDiscountsTest


class DiscountsTypesTest(BaseDiscountsTest):

    def test_discount_applies(self):
        '''
        Create a flat $5 discount and test that it applies
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount()
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s, s.getBasePrice() - 5)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal - 5
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 5)
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [test_combo.name, ])

    def test_voucherid_applies(self):
        '''
        Apply a flat $5 discount by passing a voucher code
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(voucherId='ZYX987')
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s, s.getBasePrice() - 5, voucherId='ZYX987')
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal - 5
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 5)
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [test_combo.name, ])

    def test_earlybird(self):
        '''
        Create an early registration discount that requires three day
        advance registration and ensure that it works more than
        three days in advance.
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(daysInAdvanceRequired=3)
        s = self.create_series(
            pricingTier=self.defaultPricing,
            startTime=timezone.now() + timedelta(days=4)
        )

        response = self.register_to_check_discount(s, s.getBasePrice() - 5)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal - 5
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 5)
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [test_combo.name, ])

    def test_allwithinpointgroup(self):
        '''
        Set a discount to apply to an entire point group and check that the price
        is still the flat price
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(quantity=1, allWithinPointGroup=True)
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s, s.getBasePrice() - 5)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal - 5
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 5)
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [test_combo.name, ])

    def test_dollarDiscount(self):
        '''
        Create a $10 off discount and check that it applies appropriately
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(
            discountType=DiscountCombo.DiscountType.dollarDiscount,
            dollarDiscount=10
        )
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s, s.getBasePrice() - 10)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal - 10
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 10)
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [test_combo.name, ])

    def test_percentDiscount(self):
        '''
        Create a 50% off discount and check that it applies correctly.
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(
            discountType=DiscountCombo.DiscountType.percentDiscount,
            percentDiscount=50,
            percentUniversallyApplied=False
        )
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s, s.getBasePrice()*0.5)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, 0.5 * invoice.grossTotal
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(
            response.context_data.get('total_discount_amount'),
            0.5 * invoice.grossTotal
        )
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [test_combo.name, ])

    def test_addOnItem(self):
        '''
        Create a free add-on item and ensure that it is applied correctly.
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(
            discountType=DiscountCombo.DiscountType.addOn,
            name='Test Free Add-On',
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
        self.assertTrue(response.context_data.get('addonItems'))
        self.assertFalse(response.context_data.get('discount_codes'))

    def test_discountmakesitfree(self):
        '''
        Make the dollar discount larger than the base price and check that
        the registration is free, that the registration is processed and that
        a $0 invoice is created.
        '''

        updateConstant('general__discountsEnabled', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        test_combo, test_component = self.create_discount(
            discountType=DiscountCombo.DiscountType.dollarDiscount,
            dollarDiscount=s.getBasePrice() + 10
        )

        response = self.register_to_check_discount(s, 0)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(invoice.total, 0)
        self.assertEqual(response.context_data.get('zero_balance'), True)
        self.assertEqual(response.context_data.get('total_discount_amount'), s.getBasePrice())
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [test_combo.name, ])

        # Since the above registration was free, check that the registration actually
        # processed, and that there exists a paid Invoice for $0
        finalReg = response.context_data.get('registration')
        invoice = response.context_data.get('invoice')
        self.assertTrue(finalReg)
        self.assertTrue(finalReg.invoice)
        self.assertEqual(finalReg.invoice, invoice)
        self.assertTrue(invoice.status == Invoice.PaymentStatus.paid)
        self.assertEqual(invoice.outstandingBalance, 0)
        self.assertEqual(invoice.total, 0)
        self.assertTrue(finalReg.final)

        # Check that the invoice no longer has an expiration date
        self.assertIsNone(invoice.expirationDate)

        # Check that the RegistrationDiscount associated with this registration
        # has been applied.
        self.assertTrue(finalReg.registrationdiscount_set.first().applied)

        # Show that multiple registrations by the same customer are not permitted
        response = self.register_to_check_discount(s)
        self.assertIn(
            'You are already registered for',
            ' '.join(response.context_data['form'].errors.get('__all__'))
        )

    def test_largerdiscountapplies(self):
        '''
        Create both a $10 discount and a $20 discount, and ensure that the
        larger discount applies
        '''

        updateConstant('general__discountsEnabled', True)
        s = self.create_series(pricingTier=self.defaultPricing)
        test_combo, test_component = self.create_discount(
            discountType=DiscountCombo.DiscountType.dollarDiscount,
            dollarDiscount=10
        )
        bigger_combo, bigger_component = self.create_discount(
            discountType=DiscountCombo.DiscountType.dollarDiscount,
            dollarDiscount=20,
            name='Bigger Discount'
        )

        response = self.register_to_check_discount(s, s.getBasePrice() - 20)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal - 20
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 20)
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [bigger_combo.name, ])
