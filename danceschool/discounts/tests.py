from django.core.urlresolvers import reverse
from django.utils import timezone

from datetime import timedelta

from danceschool.core.constants import REG_VALIDATION_STR, updateConstant
from danceschool.core.utils.tests import DefaultSchoolTestCase
from danceschool.core.models import Invoice, TemporaryRegistration

from .models import PointGroup, PricingTierGroup, DiscountCategory, DiscountCombo, DiscountComboComponent


class BaseDiscountsTest(DefaultSchoolTestCase):

    def create_discount(self,**kwargs):
        '''
        This method just creates the necessary objects to create a simple discount
        with a single required component.
        '''

        test_group, created = PointGroup.objects.get_or_create(name=kwargs.get('pointGroupName','Test points'))
        pt_group, created = PricingTierGroup.objects.get_or_create(
            group=test_group,
            pricingTier=self.defaultPricing,
            points=kwargs.get('pricingTierGroupPoints', 5),
        )

        # Create a flat price combo that just knocks $5 off the regular price
        test_combo = DiscountCombo(
            name=kwargs.get('name','Test Discount'),
            category=kwargs.get('category',DiscountCategory.objects.get(id=1)),
            discountType=kwargs.get('discountType',DiscountCombo.DiscountType.flatPrice),
            onlinePrice=kwargs.get('onlinePrice',self.defaultPricing.onlinePrice - 5),
            doorPrice=kwargs.get('doorPrice',self.defaultPricing.doorPrice - 5),
            dollarDiscount=kwargs.get('dollarDiscount',10),
            percentDiscount=kwargs.get('percentDiscount',50),
            percentUniversallyApplied=kwargs.get('percentUniversallyApplied',False),
            active=kwargs.get('active',True),
            newCustomersOnly=kwargs.get('newCustomersOnly',False),
            daysInAdvanceRequired=kwargs.get('daysInAdvanceRequired',None),
            expirationDate=kwargs.get('expirationDate',None),
        )
        test_combo.save()

        test_component = DiscountComboComponent.objects.create(
            discountCombo=test_combo,
            pointGroup=test_group,
            quantity=kwargs.get('quantity',5),
            allWithinPointGroup=kwargs.get('allWithinPointGroup',False),
        )
        return (test_combo, test_component)

    def register_to_check_discount(self,series):
        '''
        This method makes it easy to determine whether discounts are working
        correctly for a single class registration
        '''

        s = series

        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code,200)
        self.assertIn(s, response.context['regOpenSeries'])

        # Sign up for the series, and check that we proceed to the student information page.
        # Because of the way that roles are encoded on this form, we just grab the value to pass
        # from the form itself.
        post_data = {'event_%s' % s.id: response.context_data['form'].fields['event_%s' % s.id].choices[0][0]}

        response = self.client.post(reverse('registration'),post_data,follow=True)
        self.assertEqual(response.redirect_chain,[(reverse('getStudentInfo'), 302)])

        tr = TemporaryRegistration.objects.get(id=self.client.session[REG_VALIDATION_STR].get('temporaryRegistrationId'))
        self.assertTrue(tr.temporaryeventregistration_set.filter(event__id=s.id).exists())

        # Check that the student info page lists the correct item amounts and subtotal
        # with no discounts applied
        self.assertEqual(tr.temporaryeventregistration_set.get(event__id=s.id).price, s.getBasePrice())
        self.assertEqual(response.context_data.get('subtotal'), s.getBasePrice())

        # Continue to the summary page
        post_data = {
            'firstName': 'Discounted',
            'lastName': 'Customer',
            'email': 'test@customer.com',
            'agreeToPolicies': True,
        }
        return self.client.post(reverse('getStudentInfo'),post_data,follow=True)


class DiscountsConditionsTest(BaseDiscountsTest):

    def test_inactive_discount(self):
        '''
        Make a discount inactive and make sure that it doesn't work
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(active=False)
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s)
        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'),response.context_data.get('totalPrice'))
        self.assertEqual(response.context_data.get('is_free'),False)
        self.assertEqual(response.context_data.get('total_discount_amount'),0)
        self.assertFalse(response.context_data.get('addonItems'))
        self.assertFalse(response.context_data.get('discount_codes'))

    def test_expired_discount(self):
        '''
        Create an expired discount and make sure that it doesn't work.
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(expirationDate=timezone.now() + timedelta(days=-1))
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s)
        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'),response.context_data.get('totalPrice'))
        self.assertEqual(response.context_data.get('is_free'),False)
        self.assertEqual(response.context_data.get('total_discount_amount'),0)
        self.assertFalse(response.context_data.get('addonItems'))
        self.assertFalse(response.context_data.get('discount_codes'))

    def test_discounts_disabled(self):
        ''' Disable discounts and check that they don't work anymore '''

        updateConstant('general__discountsEnabled', False)
        test_combo, test_component = self.create_discount()
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s)
        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'),response.context_data.get('totalPrice'))
        self.assertEqual(response.context_data.get('is_free'),False)
        self.assertEqual(response.context_data.get('total_discount_amount'),0)
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

        response = self.register_to_check_discount(s)
        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'),response.context_data.get('totalPrice'))
        self.assertEqual(response.context_data.get('is_free'),False)
        self.assertEqual(response.context_data.get('total_discount_amount'),0)
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
        s = self.create_series(pricingTier=self.defaultPricing,startTime=timezone.now() + timedelta(days=1))

        response = self.register_to_check_discount(s)
        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'),response.context_data.get('totalPrice'))
        self.assertEqual(response.context_data.get('is_free'),False)
        self.assertEqual(response.context_data.get('total_discount_amount'),0)
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

        response = self.register_to_check_discount(s)
        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'),response.context_data.get('totalPrice') - 5)
        self.assertEqual(response.context_data.get('is_free'),False)
        self.assertEqual(response.context_data.get('total_discount_amount'),5)
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [test_combo.name,])

    def test_earlybird(self):
        '''
        Create an early registration discount that requires three day
        advance registration and ensure that it works more than
        three days in advance.
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(daysInAdvanceRequired=3)
        s = self.create_series(pricingTier=self.defaultPricing,startTime=timezone.now() + timedelta(days=4))

        response = self.register_to_check_discount(s)
        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'),response.context_data.get('totalPrice') - 5)
        self.assertEqual(response.context_data.get('is_free'),False)
        self.assertEqual(response.context_data.get('total_discount_amount'),5)
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [test_combo.name,])

    def test_allwithinpointgroup(self):
        '''
        Set a discount to apply to an entire point group and check that the price
        is still the flat price
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(quantity=1, allWithinPointGroup=True)
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s)
        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'),response.context_data.get('totalPrice') - 5)
        self.assertEqual(response.context_data.get('is_free'),False)
        self.assertEqual(response.context_data.get('total_discount_amount'),5)
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [test_combo.name,])

    def test_dollarDiscount(self):
        '''
        Create a $10 off discount and check that it applies appropriately
        '''

        updateConstant('general__discountsEnabled', True)
        test_combo, test_component = self.create_discount(discountType=DiscountCombo.DiscountType.dollarDiscount, dollarDiscount=10)
        s = self.create_series(pricingTier=self.defaultPricing)

        response = self.register_to_check_discount(s)
        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'),response.context_data.get('totalPrice') - 10)
        self.assertEqual(response.context_data.get('is_free'),False)
        self.assertEqual(response.context_data.get('total_discount_amount'),10)
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [test_combo.name,])

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

        response = self.register_to_check_discount(s)
        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'),0.5 * response.context_data.get('totalPrice'))
        self.assertEqual(response.context_data.get('is_free'),False)
        self.assertEqual(response.context_data.get('total_discount_amount'),0.5 * response.context_data.get('totalPrice'))
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [test_combo.name,])

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

        response = self.register_to_check_discount(s)

        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'), response.context_data.get('totalPrice'))
        self.assertEqual(response.context_data.get('is_free'),False)
        self.assertEqual(response.context_data.get('total_discount_amount'),0)
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
        test_combo, test_component = self.create_discount(discountType=DiscountCombo.DiscountType.dollarDiscount, dollarDiscount=s.getBasePrice() + 10)

        response = self.register_to_check_discount(s)
        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'),0)
        self.assertEqual(response.context_data.get('is_free'),True)
        self.assertEqual(response.context_data.get('total_discount_amount'),s.getBasePrice())
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [test_combo.name,])

        # Since the above registration was free, check that the registration actually
        # processed, and that there exists a paid Invoice for $0
        finalReg = getattr(response.context_data.get('registration'),'registration')
        self.assertTrue(finalReg)
        self.assertEqual(finalReg.netPrice, 0)
        self.assertTrue(finalReg.invoice)
        self.assertTrue(finalReg.invoice.status == Invoice.PaymentStatus.paid)
        self.assertEqual(finalReg.invoice.outstandingBalance, 0)
        self.assertEqual(finalReg.invoice.total, 0)

        # Check that the associated temporary registration is now expired
        self.assertTrue(finalReg.temporaryRegistration.expirationDate <= timezone.now())

        # Show that multiple registrations by the same customer are not permitted
        response = self.register_to_check_discount(s)
        self.assertIn('You are already registered for',' '.join(response.context_data['form'].errors.get('__all__')))

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

        response = self.register_to_check_discount(s)
        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'),response.context_data.get('totalPrice') - 20)
        self.assertEqual(response.context_data.get('is_free'),False)
        self.assertEqual(response.context_data.get('total_discount_amount'),20)
        self.assertFalse(response.context_data.get('addonItems'))

        discount_codes = response.context_data.get('discount_codes')
        self.assertEqual([x[0] for x in discount_codes], [bigger_combo.name,])
