import json
import unittest

from django.forms.models import model_to_dict
from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from danceschool.core.constants import REG_VALIDATION_STR, updateConstant
from danceschool.core.tests.defaults import DefaultSchoolTestCase
from danceschool.core.models import Invoice, Registration
from danceschool.vouchers.models import Voucher

from .models import (
    PointGroup, PricingTierGroup, DiscountCategory, DiscountCombo, DiscountComboComponent
)


class BaseDiscountsTest(DefaultSchoolTestCase):

    def create_discount(self, **kwargs):
        '''
        This method just creates the necessary objects to create a simple discount
        with a single required component.
        '''

        test_group, created = PointGroup.objects.get_or_create(
            name=kwargs.get('pointGroupName', 'Test points')
        )
        pt_group, created = PricingTierGroup.objects.get_or_create(
            group=test_group,
            pricingTier=self.defaultPricing,
            points=kwargs.get('pricingTierGroupPoints', 5),
        )

        # Create a flat price combo that just knocks $5 off the regular price
        test_combo = DiscountCombo(
            name=kwargs.get('name', 'Test Discount'),
            category=kwargs.get('category', DiscountCategory.objects.get(id=1)),
            voucherId=kwargs.get('voucherId', None),
            discountType=kwargs.get('discountType', DiscountCombo.DiscountType.flatPrice),
            onlinePrice=kwargs.get('onlinePrice', self.defaultPricing.onlinePrice - 5),
            doorPrice=kwargs.get('doorPrice', self.defaultPricing.doorPrice - 5),
            dollarDiscount=kwargs.get('dollarDiscount', 10),
            percentDiscount=kwargs.get('percentDiscount', 50),
            percentUniversallyApplied=kwargs.get('percentUniversallyApplied', False),
            active=kwargs.get('active', True),
            availableOnline=kwargs.get('availableOnline', True),
            availableAtDoor=kwargs.get('availableAtDoor', True),
            newCustomersOnly=kwargs.get('newCustomersOnly', False),
            daysInAdvanceRequired=kwargs.get('daysInAdvanceRequired', None),
            expirationDate=kwargs.get('expirationDate', None),
        )
        test_combo.save()

        test_component = DiscountComboComponent.objects.create(
            discountCombo=test_combo,
            pointGroup=test_group,
            quantity=kwargs.get('quantity', 5),
            allWithinPointGroup=kwargs.get('allWithinPointGroup', False),
        )
        return (test_combo, test_component)

    def register_to_check_discount(
        self, series, expected_amount=None, payAtDoor=False,
        voucherId=None
    ):
        '''
        This method makes it easy to determine whether discounts are working
        correctly for a single class registration
        '''

        s = series

        if payAtDoor:
            self.client.force_login(self.superuser)

        sku = 'EVENT_{}_GENERAL'.format(s.id)
        cart_data = {
            'items': [{'item_type': 'Event', 'item_id': s.id, 'sku': sku, 'quantity': 1}],
            'checkout': True,
        }
        if payAtDoor:
            cart_data['payAtDoor'] = True
        if voucherId:
            cart_data['discount_code'] = voucherId

        response = self.client.post(
            reverse('cart'),
            data=json.dumps(cart_data),
            content_type='application/json',
            follow=True,
        )
        self.assertEqual(response.redirect_chain, [(reverse('getStudentInfo'), 302)])

        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR].get('invoice_id')
        )
        tr = Registration.objects.filter(invoice=invoice).first()
        self.assertTrue(tr.eventregistration_set.filter(event__id=s.id).exists())
        self.assertFalse(tr.final)

        # Check that the student info page lists the correct subtotal with
        # the discount applied
        self.assertEqual(invoice.grossTotal, s.getBasePrice(payAtDoor=payAtDoor))
        if expected_amount is not None:
            self.assertEqual(
                response.context_data.get('invoice').outstandingBalance, expected_amount
            )

        # Continue to the summary page
        post_data = {
            'firstName': 'Discounted',
            'lastName': 'Customer',
            'email': 'test@customer.com',
            'agreeToPolicies': True,
        }
        if voucherId:
            post_data['gift'] = voucherId
        return self.client.post(reverse('getStudentInfo'), post_data, follow=True)


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

    @unittest.expectedFailure
    def test_shared_code_not_double_subtracted(self):
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
