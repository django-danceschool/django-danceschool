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

    def test_merch_checkout_with_quantity_greater_than_one(self):
        '''Quantity > 1 yields a single MerchOrderItem carrying that quantity.'''
        from danceschool.merch.models import MerchOrder, MerchOrderItem
        response = self._door_cart_post(
            items=[{
                'item_type': 'MerchItem',
                'item_id': self.item.id,
                'sku': self.variant.sku,
                'quantity': 3,
            }],
            checkout=True,
        )
        self.assertRedirects(
            response, reverse('getStudentInfo'), fetch_redirect_response=False
        )
        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR]['invoice_id']
        )
        self.assertEqual(invoice.grossTotal, self.item.defaultPrice * 3)
        order = MerchOrder.objects.get(invoice=invoice)
        order_items = MerchOrderItem.objects.filter(order=order, item=self.variant)
        self.assertEqual(order_items.count(), 1)
        self.assertEqual(order_items.first().quantity, 3)

    def test_merch_duplicate_sku_in_cart_is_validation_error(self):
        '''Duplicate SKU lines are rejected cleanly rather than raising a server error.'''
        line = {
            'item_type': 'MerchItem',
            'item_id': self.item.id,
            'sku': self.variant.sku,
            'quantity': 1,
        }
        response = self._door_cart_post(items=[line, dict(line)], checkout=True)
        self.assertEqual(response.status_code, 400)

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


class MerchStudentInfoViewTest(DefaultSchoolTestCase):
    '''
    Tests that StudentInfoView correctly reflects the contents of a
    merch-only cart after checkout.  Specifically checks that
    InvoiceItem.description and InvoiceItem.grossTotal match the
    selected merchandise variant, not any unrelated Event that might
    share the same primary key.
    '''

    def setUp(self):
        self.client.force_login(self.superuser)
        self.item = MerchItem.objects.create(
            name='Test Jacket',
            category=None,
            defaultPrice=45,
            disabled=False,
        )
        self.variant = MerchItemVariant.objects.create(
            item=self.item,
            sku='JACKET-XL',
            name='X-Large',
            originalQuantity=10,
        )

    def _checkout(self, item, variant):
        '''
        Submit a merch-only door cart with checkout=True and return the
        resulting GET response from StudentInfoView.
        '''
        checkout_response = self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{
                    'item_type': 'MerchItem',
                    'item_id': item.id,
                    'sku': variant.sku,
                    'quantity': 1,
                }],
                'checkout': True,
                'payAtDoor': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(
            checkout_response.status_code, 302,
            'Cart checkout must redirect to StudentInfoView.',
        )
        return self.client.get(reverse('getStudentInfo'))

    def _get_invoice(self):
        invoice_id = self.client.session[REG_VALIDATION_STR]['invoice_id']
        return Invoice.objects.get(id=invoice_id)

    # --- Basic correctness ---

    def test_student_info_view_renders_after_merch_checkout(self):
        '''StudentInfoView must respond with 200 after a merch-only cart checkout.'''
        response = self._checkout(self.item, self.variant)
        self.assertEqual(response.status_code, 200)

    def test_invoice_item_description_is_merch_variant_full_name(self):
        '''
        The InvoiceItem created during checkout must carry the variant full
        name (e.g. "Test Jacket: X-Large"), not an event name.
        '''
        self._checkout(self.item, self.variant)
        invoice = self._get_invoice()
        items = list(invoice.invoiceitem_set.all())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].description, self.variant.fullName)

    def test_invoice_item_price_matches_merch_default_price(self):
        '''
        The InvoiceItem grossTotal must equal the merchandise item's
        defaultPrice, not the price of any unrelated Event.
        '''
        self._checkout(self.item, self.variant)
        invoice = self._get_invoice()
        items = list(invoice.invoiceitem_set.all())
        self.assertEqual(len(items), 1)
        self.assertAlmostEqual(items[0].grossTotal, self.item.defaultPrice, places=2)

    def test_no_registration_created_for_merch_only_cart(self):
        '''A merch-only cart must not create a Registration object.'''
        self._checkout(self.item, self.variant)
        invoice = self._get_invoice()
        self.assertFalse(Registration.objects.filter(invoice=invoice).exists())

    # --- pk-collision regression ---

    def test_pk_collision_invoice_item_description_is_merch_not_event(self):
        '''
        Regression: when a MerchItem and an Event share the same integer pk,
        the checkout must produce an InvoiceItem whose description comes from
        the merch variant, not the event.
        '''
        series = self.create_series()

        # Force the MerchItem to share the Event's pk (possible because they
        # live in separate database tables).
        collision_item = MerchItem(
            pk=series.pk,
            name='Collision Hoodie',
            defaultPrice=30,
            disabled=False,
        )
        collision_item.save()
        collision_variant = MerchItemVariant.objects.create(
            item=collision_item,
            sku='HOODIE-COLL',
            name='One Size',
            originalQuantity=5,
        )

        self._checkout(collision_item, collision_variant)
        invoice = self._get_invoice()
        items = list(invoice.invoiceitem_set.all())

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].description, collision_variant.fullName)
        self.assertNotEqual(items[0].description, series.name)

    def test_pk_collision_invoice_item_price_is_merch_not_event(self):
        '''
        Regression: with a pk collision between a MerchItem and an Event,
        the InvoiceItem grossTotal must equal the merch price, not the event
        base price.
        '''
        series = self.create_series()

        collision_item = MerchItem(
            pk=series.pk,
            name='Collision Cap',
            defaultPrice=15,
            disabled=False,
        )
        collision_item.save()
        collision_variant = MerchItemVariant.objects.create(
            item=collision_item,
            sku='CAP-COLL',
            name='One Size',
            originalQuantity=5,
        )

        self._checkout(collision_item, collision_variant)
        invoice = self._get_invoice()
        items = list(invoice.invoiceitem_set.all())

        self.assertEqual(len(items), 1)
        self.assertAlmostEqual(items[0].grossTotal, collision_item.defaultPrice, places=2)
        self.assertNotAlmostEqual(
            items[0].grossTotal, series.getBasePrice(), places=2,
            msg='Invoice price must not match the colliding event base price.',
        )

    def test_pk_collision_no_spurious_registration(self):
        '''
        Regression: a merch-only cart must not create a Registration even
        when the MerchItem pk collides with an existing Event pk.
        '''
        series = self.create_series()

        collision_item = MerchItem(
            pk=series.pk,
            name='Collision Bag',
            defaultPrice=20,
            disabled=False,
        )
        collision_item.save()
        collision_variant = MerchItemVariant.objects.create(
            item=collision_item,
            sku='BAG-COLL',
            name='Standard',
            originalQuantity=5,
        )

        self._checkout(collision_item, collision_variant)
        invoice = self._get_invoice()
        self.assertFalse(
            Registration.objects.filter(invoice=invoice).exists(),
            'A merch-only cart must not create a Registration.',
        )


class MerchItemAdminInventoryColumnTest(DefaultSchoolTestCase):
    '''
    The merchandise item changelist shows each variant's current inventory.
    '''

    def setUp(self):
        self.item = MerchItem.objects.create(
            name='Test Hoodie', category=None, defaultPrice=35, disabled=False,
        )
        self.small = MerchItemVariant.objects.create(
            item=self.item, sku='HOODIE-SM', name='Small', originalQuantity=7,
        )
        self.large = MerchItemVariant.objects.create(
            item=self.item, sku='HOODIE-LG', name='Large <b>', originalQuantity=12,
        )
        self.empty_item = MerchItem.objects.create(
            name='Test Sticker', category=None, defaultPrice=2, disabled=False,
        )

    def _changelist(self):
        self.client.force_login(self.superuser)
        response = self.client.get('/admin/merch/merchitem/')
        self.assertEqual(response.status_code, 200)
        return response

    def test_variants_and_quantities_listed_in_order(self):
        html = self._changelist().content.decode()
        self.assertIn('Inventory by variant', html)
        self.assertIn('merch/admin/inventory.css', html)
        small = html.index('>Small</span>')
        large = html.index('>Large &lt;b&gt;</span>')
        self.assertLess(small, large)
        # Each line is name, dotted leader, then the quantity.
        self.assertRegex(
            html,
            r'>Small</span><span class="merch-inventory-leader"></span>'
            r'<span class="merch-inventory-qty">7</span>'
        )
        self.assertRegex(
            html,
            r'>Large &lt;b&gt;</span><span class="merch-inventory-leader"></span>'
            r'<span class="merch-inventory-qty">12</span>'
        )

    def test_inventory_uses_list_not_nested_table(self):
        '''A nested table would pick up the changelist's alternating row colors.'''
        html = self._changelist().content.decode()
        self.assertIn('<ul class="merch-inventory">', html)

    def test_variant_names_are_escaped(self):
        html = self._changelist().content.decode()
        self.assertNotIn('Large <b>', html)

    def test_item_without_variants_is_handled(self):
        self.assertContains(self._changelist(), 'No variants')

    def test_quantity_reflects_adjustments(self):
        from .models import MerchQuantityAdjustment
        MerchQuantityAdjustment.objects.create(variant=self.small, amount=-3)
        html = self._changelist().content.decode()
        self.assertRegex(html, r'>Small</span><span[^>]*></span><span[^>]*>4</span>')


class MerchItemCategoryAdminTest(DefaultSchoolTestCase):
    '''
    Merchandise categories can be managed in the admin, including from the
    category dropdown on the merchandise item form.
    '''

    def setUp(self):
        from .models import MerchItemCategory
        self.shirts = MerchItemCategory.objects.create(name='Shirts')
        self.stickers = MerchItemCategory.objects.create(name='Stickers')
        self.hoodie = MerchItem.objects.create(
            name='Test Hoodie', category=self.shirts, defaultPrice=35,
        )
        self.tee = MerchItem.objects.create(
            name='Test Tee', category=self.shirts, defaultPrice=20,
        )
        self.sticker = MerchItem.objects.create(
            name='Test Sticker', category=self.stickers, defaultPrice=2,
        )
        self.client.force_login(self.superuser)

    def test_category_changelist_shows_names_and_item_counts(self):
        response = self.client.get('/admin/merch/merchitemcategory/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertRegex(html, r'Shirts</a></th><td[^>]*>2</td>')
        self.assertRegex(html, r'Stickers</a></th><td[^>]*>1</td>')

    def test_category_can_be_added_in_admin(self):
        from .models import MerchItemCategory
        response = self.client.post(
            '/admin/merch/merchitemcategory/add/', {'name': 'Posters'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(MerchItemCategory.objects.filter(name='Posters').exists())

    def test_item_form_offers_add_category_link(self):
        '''Registering the category admin adds the "+" button to the dropdown.'''
        response = self.client.get('/admin/merch/merchitem/add/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'add_id_category')

    def test_item_change_form_preselects_category(self):
        response = self.client.get('/admin/merch/merchitem/%s/change/' % self.hoodie.id)
        self.assertContains(
            response, '<option value="%s" selected>Shirts</option>' % self.shirts.id
        )

    def test_item_changelist_shows_and_filters_by_category(self):
        response = self.client.get('/admin/merch/merchitem/')
        self.assertContains(response, 'Shirts')
        response = self.client.get(
            '/admin/merch/merchitem/', {'category__id__exact': self.stickers.id}
        )
        self.assertContains(response, 'Test Sticker')
        self.assertNotContains(response, 'Test Hoodie')
        self.assertNotContains(response, 'Test Tee')

    def test_item_can_be_saved_without_category(self):
        '''Category is optional: an item with none must pass admin form validation.'''
        from django.forms import modelform_factory
        Form = modelform_factory(MerchItem, fields=['name', 'category', 'defaultPrice', 'salesTaxRate'])
        form = Form({'name': 'Uncategorized', 'defaultPrice': 5, 'salesTaxRate': 0})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save().category)

    def test_deleting_category_leaves_items_uncategorized(self):
        self.shirts.delete()
        self.hoodie.refresh_from_db()
        self.assertIsNone(self.hoodie.category)
        self.assertEqual(self.client.get('/admin/merch/merchitem/').status_code, 200)

    def test_category_plural_name(self):
        from .models import MerchItemCategory
        self.assertEqual(str(MerchItemCategory._meta.verbose_name_plural), 'Merchandise categories')
