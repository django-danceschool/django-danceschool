import json

from django.urls import reverse

from danceschool.core.constants import REG_VALIDATION_STR
from danceschool.core.models import Invoice, Registration
from danceschool.core.tests.defaults import DefaultSchoolTestCase

from .models import MerchItem, MerchItemVariant


class MerchPurchasableItemsTest(DefaultSchoolTestCase):
    '''
    Tests for merch item visibility in the PurchasableItemsView API.
    Merchandise is only available at the door, so all tests that expect items
    to appear must use payAtDoor=true with a door-permitted user.
    '''

    def setUp(self):
        self.item = MerchItem.objects.create(
            name='Test T-Shirt',
            category=None,
            defaultPrice=20,
            disabled=False,
        )
        self.variant_sm = MerchItemVariant.objects.create(
            item=self.item,
            sku='TSHIRT-SM',
            name='Small',
            originalQuantity=10,
        )
        self.variant_lg = MerchItemVariant.objects.create(
            item=self.item,
            sku='TSHIRT-LG',
            name='Large',
            originalQuantity=5,
        )

    def test_merch_absent_for_online_registration(self):
        '''Merch items must not appear in the API for non-door requests.'''
        response = self.client.get(reverse('purchasableItems'))
        self.assertEqual(response.status_code, 200)
        ids = [item.get('id') for item in response.json().get('results', [])]
        self.assertNotIn(self.item.id, ids)

    def test_merch_shown_at_door(self):
        '''Merch items appear in the API when payAtDoor=true and user has permission.'''
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('purchasableItems') + '?payAtDoor=true')
        self.assertEqual(response.status_code, 200)
        ids = [item.get('id') for item in response.json().get('results', [])]
        self.assertIn(self.item.id, ids)

    def test_merch_variants_exposed_at_door(self):
        '''Each MerchItemVariant appears as a variant entry with its SKU.'''
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('purchasableItems') + '?payAtDoor=true')
        results = response.json().get('results', [])
        merch = next(x for x in results if x.get('id') == self.item.id)
        variant_skus = [v['sku'] for v in merch['variants']]
        self.assertIn('TSHIRT-SM', variant_skus)
        self.assertIn('TSHIRT-LG', variant_skus)

    def test_sold_out_variant_excluded(self):
        '''Variants marked soldOut should not appear in the listing.'''
        # Use update() to bypass MerchItemVariant.save() which recalculates
        # soldOut from currentInventory and would reset it to False.
        MerchItemVariant.objects.filter(pk=self.variant_sm.pk).update(soldOut=True)
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('purchasableItems') + '?payAtDoor=true')
        results = response.json().get('results', [])
        merch = next(x for x in results if x.get('id') == self.item.id)
        variant_skus = [v['sku'] for v in merch['variants']]
        self.assertNotIn('TSHIRT-SM', variant_skus)
        self.assertIn('TSHIRT-LG', variant_skus)

    def test_merch_not_shown_without_door_permission(self):
        '''Non-staff user passing payAtDoor=true must not see merch.'''
        self.client.force_login(self.nonStaffUser)
        response = self.client.get(reverse('purchasableItems') + '?payAtDoor=true')
        ids = [item.get('id') for item in response.json().get('results', [])]
        self.assertNotIn(self.item.id, ids)


class MerchCartCheckoutTest(DefaultSchoolTestCase):
    '''
    Tests for adding merchandise to a cart and checking out at the door.
    '''

    def setUp(self):
        self.item = MerchItem.objects.create(
            name='Test Hoodie',
            category=None,
            defaultPrice=35,
            disabled=False,
        )
        self.variant = MerchItemVariant.objects.create(
            item=self.item,
            sku='HOODIE-MD',
            name='Medium',
            originalQuantity=10,
        )

    def _door_cart_post(self, items, checkout=False):
        self.client.force_login(self.superuser)
        return self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': items,
                'checkout': checkout,
                'payAtDoor': True,
            }),
            content_type='application/json',
        )

    def test_merch_item_accepted_in_door_cart(self):
        response = self._door_cart_post([{
            'item_type': 'MerchItem',
            'item_id': self.item.id,
            'sku': self.variant.sku,
            'quantity': 1,
        }])
        self.assertEqual(response.status_code, 200)
        items = response.json().get('items', [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['sku'], self.variant.sku)

    def test_merch_checkout_creates_invoice_with_merch_order(self):
        from danceschool.merch.models import MerchOrder
        response = self._door_cart_post(
            items=[{
                'item_type': 'MerchItem',
                'item_id': self.item.id,
                'sku': self.variant.sku,
                'quantity': 1,
            }],
            checkout=True,
        )
        self.assertRedirects(
            response, reverse('getStudentInfo'), fetch_redirect_response=False
        )
        invoice_id = self.client.session[REG_VALIDATION_STR].get('invoice_id')
        self.assertIsNotNone(invoice_id)
        invoice = Invoice.objects.get(id=invoice_id)
        self.assertEqual(invoice.grossTotal, self.item.defaultPrice)
        self.assertTrue(MerchOrder.objects.filter(invoice=invoice).exists())

    def test_merch_checkout_creates_merch_order_item(self):
        from danceschool.merch.models import MerchOrder, MerchOrderItem
        self._door_cart_post(
            items=[{
                'item_type': 'MerchItem',
                'item_id': self.item.id,
                'sku': self.variant.sku,
                'quantity': 1,
            }],
            checkout=True,
        )
        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR]['invoice_id']
        )
        order = MerchOrder.objects.get(invoice=invoice)
        self.assertTrue(
            MerchOrderItem.objects.filter(order=order, item=self.variant).exists()
        )

    def test_merch_rejected_for_online_cart(self):
        '''Merch items must be rejected when payAtDoor is not set.'''
        response = self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{
                    'item_type': 'MerchItem',
                    'item_id': self.item.id,
                    'sku': self.variant.sku,
                    'quantity': 1,
                }],
                'checkout': False,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
