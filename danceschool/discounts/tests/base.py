import json

from django.urls import reverse

from dynamic_preferences.registries import global_preferences_registry

from danceschool.core.constants import REG_VALIDATION_STR, updateConstant
from danceschool.core.tests.defaults import DefaultSchoolTestCase
from danceschool.core.models import Invoice, PricingTier, Registration

from ..models import (
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


class DiscountAllocationBase(BaseDiscountsTest):
    '''
    Set up and helper methods for tests of how discounts are allocated among
    the items on an invoice. This class has no tests of its own. It provides
    a $10 pricing tier that earns no discount (A), and a $20 pricing tier (B)
    that is the only one in its point group.
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
