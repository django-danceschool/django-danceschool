import json
from unittest import skipUnless

from django.apps import apps
from django.forms.models import model_to_dict
from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from dynamic_preferences.registries import global_preferences_registry

from danceschool.core.constants import REG_VALIDATION_STR, updateConstant
from danceschool.core.tests.defaults import DefaultSchoolTestCase
from danceschool.core.tests.test_tax import TaxTestMixin
from danceschool.core.models import Invoice, PricingTier, Registration, EventAddOn

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


class MixedCartDiscountAllocationTest(BaseDiscountsTest):
    '''
    Reproduces a bug where a discount that applies to only some items in a
    mixed cart is allocated proportionally across ALL items by grossTotal,
    rather than being attributed to the items the discount actually covered.

    Scenario: cart contains a $10 regular series + a $20 series eligible for
    a 100% discount. Expected per-item totals after discount: $10 and $0.
    Buggy current behavior allocates the $20 discount as $6.67 off the $10
    item and $13.33 off the $20 item, leaving misleading per-item totals
    (and a wrong grand total once items have different tax rates).
    '''

    def _make_tier(self, name, price):
        return PricingTier.objects.create(
            name=name, onlinePrice=price, doorPrice=price, dropinPrice=price,
        )

    def _make_full_off_combo(self, point_group, name):
        # Uses percentDiscount (non-universal) so the discount attributes
        # to specifically-covered items rather than spreading across the
        # whole cart. flatPrice and dollarDiscount currently spread
        # proportionally (see DiscountCombo.applyAndAllocate); that's a
        # separate concern from this test.
        combo = DiscountCombo.objects.create(
            name=name,
            category=DiscountCategory.objects.get(id=1),
            discountType=DiscountCombo.DiscountType.percentDiscount,
            percentDiscount=100,
            percentUniversallyApplied=False,
            active=True,
            availableOnline=True,
            availableAtDoor=True,
        )
        DiscountComboComponent.objects.create(
            discountCombo=combo, pointGroup=point_group, quantity=5,
            allWithinPointGroup=False,
        )
        return combo

    def test_full_discount_on_one_item_does_not_affect_other_items(self):
        updateConstant('general__discountsEnabled', True)

        tier_a = self._make_tier('Cheap Tier', 10)
        tier_b = self._make_tier('Pricey Tier', 20)

        # Series A is ineligible for the discount; series B is the only
        # member of the point group the discount requires.
        s_a = self.create_series(pricingTier=tier_a)
        s_b = self.create_series(pricingTier=tier_b)

        b_only_group = PointGroup.objects.create(name='Tier B only')
        PricingTierGroup.objects.create(
            group=b_only_group, pricingTier=tier_b, points=5,
        )
        self._make_full_off_combo(b_only_group, 'Free Tier B')

        cart_data = {
            'items': [
                {
                    'item_type': 'Event', 'item_id': s_a.id,
                    'sku': f'EVENT_{s_a.id}_GENERAL', 'quantity': 1,
                },
                {
                    'item_type': 'Event', 'item_id': s_b.id,
                    'sku': f'EVENT_{s_b.id}_GENERAL', 'quantity': 1,
                },
            ],
            'checkout': True,
        }
        response = self.client.post(
            reverse('cart'),
            data=json.dumps(cart_data),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Mixed',
            'lastName': 'Cart',
            'email': 'mixed@cart.com',
            'agreeToPolicies': True,
        }, follow=True)
        # Two items in the cart → flow detours through the multi-customer
        # name form before reaching the summary page.
        self.assertEqual(
            response.redirect_chain, [(reverse('multiRegNameInfo'), 302)],
        )

        invoice_pre = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR].get('invoice_id')
        )
        reg_pre = Registration.objects.get(invoice=invoice_pre)
        name_post = {}
        for er in reg_pre.eventregistration_set.all():
            name_post['er_%s_firstName' % er.id] = 'Mixed'
            name_post['er_%s_lastName' % er.id] = 'Cart'
            name_post['er_%s_email' % er.id] = 'mixed@cart.com'

        response = self.client.post(
            reverse('multiRegNameInfo'), name_post, follow=True,
        )
        self.assertEqual(
            response.redirect_chain, [(reverse('showRegSummary'), 302)],
        )

        invoice = response.context_data.get('invoice')
        items = {it.grossTotal: it for it in invoice.invoiceitem_set.all()}

        # Sanity: the right items exist with the right gross totals.
        self.assertIn(10, items, 'Series A item with grossTotal $10 missing')
        self.assertIn(20, items, 'Series B item with grossTotal $20 missing')
        item_a = items[10]
        item_b = items[20]

        # Invoice grand total must be $10 (the regular item) regardless.
        # Use assertAlmostEqual for floating-point money math.
        self.assertAlmostEqual(
            invoice.total, 10, places=2,
            msg='Invoice total wrong after applying $20 discount to a $20 item',
        )
        self.assertEqual(
            response.context_data.get('total_discount_amount'), 20,
        )

        # The discount applied only to item B, so item A must keep its
        # full $10 total and item B must be reduced to $0.
        self.assertAlmostEqual(
            item_a.total, 10, places=2,
            msg=(
                'Item A (regular $10) should not be discounted; '
                'got {0} (suggests proportional allocation bug)'
            ).format(item_a.total),
        )
        self.assertAlmostEqual(
            item_b.total, 0, places=2,
            msg=(
                'Item B (eligible for 100% off) should be $0; '
                'got {0} (suggests proportional allocation bug)'
            ).format(item_b.total),
        )


class DiscountAllocationTest(BaseDiscountsTest):
    '''
    A discount must reduce the price of the invoice items that earned it, and
    no others (unless it is a universally-applied percentage discount). Each
    test puts a $10 series that earns no discount (A) in the cart along with
    one or more registrations for a series that does (B).
    '''

    def setUp(self):
        updateConstant('general__discountsEnabled', True)
        self.gp = global_preferences_registry.manager()

        self.tier_a = self.make_tier('Tier A', 10)
        self.tier_b = self.make_tier('Tier B', 20)
        self.group_b = PointGroup.objects.create(name='Tier B only')
        PricingTierGroup.objects.create(
            group=self.group_b, pricingTier=self.tier_b, points=5,
        )

    def tearDown(self):
        self.gp['registration__multiRegSeriesRule'] = 'N'

    def make_tier(self, name, price):
        return PricingTier.objects.create(
            name=name, onlinePrice=price, doorPrice=price, dropinPrice=price,
        )

    def make_combo(self, group=None, allWithinPointGroup=False, **kwargs):
        ''' Create a discount that is earned by one registration in the group. '''
        kwargs.setdefault('discountType', DiscountCombo.DiscountType.percentDiscount)
        combo = DiscountCombo.objects.create(
            name=kwargs.pop('name', 'Allocation Test Discount'),
            category=DiscountCategory.objects.get(id=1),
            active=True, availableOnline=True, availableAtDoor=True,
            **kwargs
        )
        DiscountComboComponent.objects.create(
            discountCombo=combo, pointGroup=group or self.group_b, quantity=5,
            allWithinPointGroup=allWithinPointGroup,
        )
        return combo

    def checkout(self, *events, **kwargs):
        '''
        Put one registration for each passed event in the cart (pass an event
        more than once for more than one registration), and proceed through to
        the summary page. Returns the summary page response.
        '''
        names = kwargs.get('names', [('Mixed', 'Cart')])
        cart_data = {
            'items': [
                {
                    'item_type': 'Event', 'item_id': event.id,
                    'sku': f'EVENT_{event.id}_GENERAL', 'quantity': 1,
                } for event in events
            ],
            'checkout': True,
        }
        if kwargs.get('discount_code'):
            cart_data['discount_code'] = kwargs['discount_code']

        response = self.client.post(
            reverse('cart'), data=json.dumps(cart_data),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.post(reverse('getStudentInfo'), {
            'firstName': names[0][0], 'lastName': names[0][1],
            'email': 'mixed@cart.com', 'agreeToPolicies': True,
        }, follow=True)

        # More than one registration means that the name of the person
        # associated with each registration is requested.
        if response.redirect_chain[-1][0] == reverse('multiRegNameInfo'):
            invoice = Invoice.objects.get(
                id=self.client.session[REG_VALIDATION_STR].get('invoice_id')
            )
            reg = Registration.objects.get(invoice=invoice)
            name_post = {}
            for idx, er in enumerate(reg.eventregistration_set.order_by('id')):
                name = names[idx % len(names)]
                name_post['er_%s_firstName' % er.id] = name[0]
                name_post['er_%s_lastName' % er.id] = name[1]
                name_post['er_%s_email' % er.id] = 'mixed@cart.com'
            response = self.client.post(
                reverse('multiRegNameInfo'), name_post, follow=True,
            )

        self.assertEqual(response.redirect_chain[-1][0], reverse('showRegSummary'))
        return response

    def items_for(self, response, event):
        ''' The invoice items for all registrations to the passed event. '''
        invoice = Invoice.objects.get(id=response.context_data['invoice'].id)
        reg = Registration.objects.get(invoice=invoice)
        return [
            er.invoiceItem for er in
            reg.eventregistration_set.filter(event=event).order_by('id')
        ]

    def assertItemTotals(self, response, event, expected):
        totals = [x.total for x in self.items_for(response, event)]
        self.assertEqual(len(totals), len(expected))
        for total, this_expected in zip(totals, expected):
            self.assertAlmostEqual(
                total, this_expected, places=2,
                msg='Item totals for %s are %s, expected %s' % (
                    event, totals, expected
                )
            )

    def test_two_registrations_for_same_event(self):
        '''
        Two people register for the discounted series on one invoice. Both of
        their items are discounted, and the other item is not.
        '''
        self.gp['registration__multiRegSeriesRule'] = 'Y'
        s_a = self.create_series(pricingTier=self.tier_a)
        s_b = self.create_series(pricingTier=self.tier_b)
        self.make_combo(percentDiscount=50, allWithinPointGroup=True)

        response = self.checkout(
            s_a, s_b, s_b, names=[('First', 'Person'), ('Second', 'Person')]
        )

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 20, places=2)
        self.assertItemTotals(response, s_a, [10])
        self.assertItemTotals(response, s_b, [10, 10])
        self.assertAlmostEqual(response.context_data['invoice'].total, 30, places=2)

    def test_dollar_discount_is_targeted(self):
        s_a = self.create_series(pricingTier=self.tier_a)
        s_b = self.create_series(pricingTier=self.tier_b)
        self.make_combo(
            discountType=DiscountCombo.DiscountType.dollarDiscount, dollarDiscount=5,
        )

        response = self.checkout(s_a, s_b)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 5, places=2)
        self.assertItemTotals(response, s_a, [10])
        self.assertItemTotals(response, s_b, [15])
        self.assertAlmostEqual(response.context_data['invoice'].total, 25, places=2)

    def test_flat_price_discount_is_targeted(self):
        s_a = self.create_series(pricingTier=self.tier_a)
        s_b = self.create_series(pricingTier=self.tier_b)
        self.make_combo(
            discountType=DiscountCombo.DiscountType.flatPrice,
            onlinePrice=12, doorPrice=12,
        )

        response = self.checkout(s_a, s_b)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 8, places=2)
        self.assertItemTotals(response, s_a, [10])
        self.assertItemTotals(response, s_b, [12])
        self.assertAlmostEqual(response.context_data['invoice'].total, 22, places=2)

    def test_universal_percent_discount_applies_to_all_items(self):
        '''
        A percentage discount that is universally applied reduces every
        eligible item, including the ones that did not earn it.
        '''
        s_a = self.create_series(pricingTier=self.tier_a)
        s_b = self.create_series(pricingTier=self.tier_b)
        self.make_combo(percentDiscount=50, percentUniversallyApplied=True)

        response = self.checkout(s_a, s_b)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 15, places=2)
        self.assertItemTotals(response, s_a, [5])
        self.assertItemTotals(response, s_b, [10])
        self.assertAlmostEqual(response.context_data['invoice'].total, 15, places=2)

    def test_summary_page_reload_gives_same_totals(self):
        s_a = self.create_series(pricingTier=self.tier_a)
        s_b = self.create_series(pricingTier=self.tier_b)
        self.make_combo(percentDiscount=50)

        response = self.checkout(s_a, s_b)
        self.assertItemTotals(response, s_a, [10])
        self.assertItemTotals(response, s_b, [10])

        response = self.client.get(reverse('showRegSummary'))
        self.assertAlmostEqual(response.context_data['total_discount_amount'], 10, places=2)
        self.assertItemTotals(response, s_a, [10])
        self.assertItemTotals(response, s_b, [10])
        self.assertAlmostEqual(response.context_data['invoice'].total, 20, places=2)


class DiscountAllocationTaxTest(TaxTestMixin, DiscountAllocationTest):
    '''
    Tax is calculated for each invoice item at its own rate, so the tax on an
    invoice is only correct if a discount is taken off the correct items.
    Series A is taxed at 10%, and series B (which earns a 50% discount) takes
    place in another jurisdiction, where it is taxed at 3%.
    '''

    def setUp(self):
        super().setUp()
        self.setUpTax()
        self.s_a = self.create_series(pricingTier=self.tier_a)
        self.s_b = self.create_series(
            pricingTier=self.tier_b, location=self.otherLocation
        )
        self.make_combo(percentDiscount=50)

    def tearDown(self):
        super().tearDown()
        self.gp['registration__buyerPaysSalesTax'] = True
        self.tearDownTax()

    def assertTaxes(self, response, expected_a, expected_b):
        item_a = self.items_for(response, self.s_a)[0]
        item_b = self.items_for(response, self.s_b)[0]
        invoice = Invoice.objects.get(id=response.context_data['invoice'].id)

        self.assertEqual(item_a.taxRate, self.SERIES_RATE)
        self.assertEqual(item_b.taxRate, self.OTHER_RATE)
        self.assertItemTotals(response, self.s_a, [10])
        self.assertItemTotals(response, self.s_b, [10])
        self.assertAlmostEqual(item_a.taxes, expected_a, places=4)
        self.assertAlmostEqual(item_b.taxes, expected_b, places=4)
        self.assertAlmostEqual(invoice.taxes, expected_a + expected_b, places=4)
        return invoice

    def test_tax_follows_discount_when_buyer_pays(self):
        self.gp['registration__buyerPaysSalesTax'] = True
        response = self.checkout(self.s_a, self.s_b)

        # 10% of $10, and 3% of the discounted price of $10.
        invoice = self.assertTaxes(response, 1.0, 0.3)
        self.assertAlmostEqual(invoice.outstandingBalance, 21.3, places=4)

    def test_tax_follows_discount_when_seller_pays(self):
        self.gp['registration__buyerPaysSalesTax'] = False
        response = self.checkout(self.s_a, self.s_b)

        # The price includes the tax.
        invoice = self.assertTaxes(response, 10 * 0.1 / 1.1, 10 * 0.03 / 1.03)
        self.assertAlmostEqual(invoice.outstandingBalance, 20, places=4)

    # These are covered by the parent class, and need not be repeated with tax.
    test_two_registrations_for_same_event = None
    test_dollar_discount_is_targeted = None
    test_flat_price_discount_is_targeted = None
    test_universal_percent_discount_applies_to_all_items = None
    test_summary_page_reload_gives_same_totals = None


@skipUnless(
    apps.is_installed('danceschool.vouchers'), 'The vouchers app is not installed.'
)
class DiscountWithVoucherTest(TaxTestMixin, DiscountAllocationTest):
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

    # These are covered by the parent class, and need not be repeated here.
    test_two_registrations_for_same_event = None
    test_dollar_discount_is_targeted = None
    test_flat_price_discount_is_targeted = None
    test_universal_percent_discount_applies_to_all_items = None
    test_summary_page_reload_gives_same_totals = None


class DiscountAddOnTest(DiscountAllocationTest):
    '''
    An event with add-ons (e.g. an all-in pass) is charged at its own price,
    which is allocated among the pass and the events it includes. Discounts
    apply to the price that is charged, not to the stand-alone prices of the
    included events.
    '''

    def setUp(self):
        super().setUp()
        self.tier_pass = self.make_tier('Pass Tier', 100)
        self.tier_included = self.make_tier('Included Tier', 50)
        self.group_pass = PointGroup.objects.create(name='Passes only')
        PricingTierGroup.objects.create(
            group=self.group_pass, pricingTier=self.tier_pass, points=5,
        )

        self.s_pass = self.create_series(pricingTier=self.tier_pass)
        self.s_one = self.create_series(pricingTier=self.tier_included)
        self.s_two = self.create_series(pricingTier=self.tier_included)
        for order, included in enumerate([self.s_one, self.s_two]):
            EventAddOn.objects.create(
                event=self.s_pass, addOnEvent=included, order=order,
                allocationType=EventAddOn.AllocationType.fixed,
                allocationAmount=20,
            )

    def test_pass_without_discount(self):
        response = self.checkout(self.s_pass)

        self.assertItemTotals(response, self.s_pass, [60])
        self.assertItemTotals(response, self.s_one, [20])
        self.assertItemTotals(response, self.s_two, [20])
        self.assertAlmostEqual(response.context_data['invoice'].total, 100, places=2)

    def test_pass_with_universal_percent_discount(self):
        ''' 50% off of a $100 pass is $50, however the price is allocated. '''
        self.make_combo(
            group=self.group_pass, percentDiscount=50, percentUniversallyApplied=True
        )
        response = self.checkout(self.s_pass)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 50, places=2)
        self.assertItemTotals(response, self.s_pass, [30])
        self.assertItemTotals(response, self.s_one, [10])
        self.assertItemTotals(response, self.s_two, [10])
        self.assertAlmostEqual(response.context_data['invoice'].total, 50, places=2)

    def test_pass_with_full_discount_is_not_negative(self):
        self.make_combo(
            group=self.group_pass, percentDiscount=100, percentUniversallyApplied=True
        )
        response = self.checkout(self.s_pass)

        self.assertAlmostEqual(response.context_data['total_discount_amount'], 100, places=2)
        self.assertItemTotals(response, self.s_pass, [0])
        self.assertItemTotals(response, self.s_one, [0])
        self.assertItemTotals(response, self.s_two, [0])
        self.assertAlmostEqual(response.context_data['invoice'].total, 0, places=2)

    # These are covered by the parent class, and need not be repeated here.
    test_two_registrations_for_same_event = None
    test_dollar_discount_is_targeted = None
    test_flat_price_discount_is_targeted = None
    test_universal_percent_discount_applies_to_all_items = None
    test_summary_page_reload_gives_same_totals = None
