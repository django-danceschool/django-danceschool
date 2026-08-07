import json
import unittest

from django.urls import reverse

from ..models import Registration, Invoice, EventRole, PricingTier
from ..models.event_addons import EventAddOn
from ..constants import updateConstant, REG_VALIDATION_STR
from .defaults import DefaultSchoolTestCase


class PurchasableItemsViewTest(DefaultSchoolTestCase):
    '''
    Tests for the PurchasableItemsView API endpoint, which returns the set of
    items available for purchase (events, merch, etc.) along with their
    serialized variants.
    '''

    def setUp(self):
        self.series = self.create_series()

    def test_returns_event_when_registration_enabled(self):
        response = self.client.get(reverse('purchasableItems'))
        self.assertEqual(response.status_code, 200)
        ids = [item.get('id') for item in response.json().get('results', [])]
        self.assertIn(self.series.id, ids)

    def test_empty_results_when_registration_disabled(self):
        updateConstant('registration__registrationEnabled', False)
        try:
            response = self.client.get(reverse('purchasableItems'))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json().get('results', []), [])
        finally:
            updateConstant('registration__registrationEnabled', True)

    def test_event_without_explicit_roles_uses_dancetype_roles(self):
        '''
        When no EventRole records exist, VariantsField falls back to the
        DanceType roles. The default test DanceType (Lindy Hop) has Lead and
        Follow, so those SKUs should appear instead of a GENERAL variant.
        '''
        lead = self.defaultDanceRoles.get(name='Lead')
        follow = self.defaultDanceRoles.get(name='Follow')
        response = self.client.get(reverse('purchasableItems'))
        item = next(
            x for x in response.json()['results'] if x.get('id') == self.series.id
        )
        skus = [v['sku'] for v in item['variants']]
        self.assertIn(f'EVENT_{self.series.id}_ROLE_{lead.id}', skus)
        self.assertIn(f'EVENT_{self.series.id}_ROLE_{follow.id}', skus)
        self.assertNotIn(f'EVENT_{self.series.id}_GENERAL', skus)
        self.assertFalse(any(v.get('dropIn') for v in item['variants']))

    def test_event_with_roles_exposes_role_variants(self):
        lead = self.defaultDanceRoles.get(name='Lead')
        follow = self.defaultDanceRoles.get(name='Follow')
        er_lead = EventRole.objects.create(event=self.series, role=lead, capacity=10)
        er_follow = EventRole.objects.create(event=self.series, role=follow, capacity=10)

        response = self.client.get(reverse('purchasableItems'))
        item = next(
            x for x in response.json()['results'] if x.get('id') == self.series.id
        )
        skus = [v['sku'] for v in item['variants']]
        self.assertIn(f'EVENT_{self.series.id}_ROLE_{lead.id}', skus)
        self.assertIn(f'EVENT_{self.series.id}_ROLE_{follow.id}', skus)
        # With roles defined there is no general admission variant
        self.assertNotIn(f'EVENT_{self.series.id}_GENERAL', skus)

    def test_dropin_variant_absent_for_online_registration(self):
        self.series.allowDropins = True
        self.series.save()
        response = self.client.get(reverse('purchasableItems'))
        item = next(
            x for x in response.json()['results'] if x.get('id') == self.series.id
        )
        self.assertFalse(any(v.get('dropIn') for v in item['variants']))

    def test_dropin_variant_shown_at_door(self):
        self.series.allowDropins = True
        self.series.save()
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('purchasableItems') + '?payAtDoor=true')
        item = next(
            x for x in response.json()['results'] if x.get('id') == self.series.id
        )
        self.assertTrue(any(v.get('dropIn') for v in item['variants']))

    def test_dropin_variant_not_shown_without_door_permission(self):
        '''
        A non-staff user passing payAtDoor=true should not receive drop-in
        variants — the permission check must prevent it.
        '''
        self.series.allowDropins = True
        self.series.save()
        self.client.force_login(self.nonStaffUser)
        response = self.client.get(reverse('purchasableItems') + '?payAtDoor=true')
        item = next(
            x for x in response.json()['results'] if x.get('id') == self.series.id
        )
        self.assertFalse(any(v.get('dropIn') for v in item['variants']))


class CartViewTest(DefaultSchoolTestCase):
    '''
    Tests for the CartView REST endpoint, which provides a persistent
    JSON-based shopping cart used for both online and at-the-door registration.
    '''

    def setUp(self):
        self.series = self.create_series()

    def _cart_post(self, items, checkout=False, extra=None, as_door=False):
        '''POST JSON to the cart endpoint. Pass as_door=True for door registrations.'''
        data = {'items': items, 'checkout': checkout}
        if as_door:
            data['payAtDoor'] = True
        if extra:
            data.update(extra)
        if as_door:
            self.client.force_login(self.superuser)
        return self.client.post(
            reverse('cart'),
            data=json.dumps(data),
            content_type='application/json',
        )

    def _general_sku(self):
        return f'EVENT_{self.series.id}_GENERAL'

    # --- Basic cart operations ---

    def test_get_returns_empty_cart(self):
        response = self.client.get(reverse('cart'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {})

    def test_post_adds_item_and_get_reflects_it(self):
        self._cart_post([
            {'item_type': 'Event', 'item_id': self.series.id,
             'sku': self._general_sku(), 'quantity': 1}
        ])
        response = self.client.get(reverse('cart'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json().get('items', [])), 1)

    def test_post_returns_validated_cart(self):
        sku = self._general_sku()
        response = self._cart_post([
            {'item_type': 'Event', 'item_id': self.series.id, 'sku': sku, 'quantity': 1}
        ])
        self.assertEqual(response.status_code, 200)
        items = response.json().get('items', [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['sku'], sku)

    def test_post_rejects_nonexistent_item(self):
        response = self._cart_post([
            {'item_type': 'Event', 'item_id': 99999,
             'sku': 'EVENT_99999_GENERAL', 'quantity': 1}
        ])
        self.assertEqual(response.status_code, 400)

    def test_delete_removes_item_from_cart(self):
        self._cart_post([
            {'item_type': 'Event', 'item_id': self.series.id,
             'sku': self._general_sku(), 'quantity': 1}
        ])
        response = self.client.delete(
            reverse('cart'),
            data=json.dumps({'item_id': self.series.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json().get('items', [])), 0)

    # --- Checkout ---

    def test_checkout_creates_invoice_and_redirects(self):
        response = self._cart_post(
            items=[{'item_type': 'Event', 'item_id': self.series.id,
                    'sku': self._general_sku(), 'quantity': 1}],
            checkout=True,
        )
        self.assertRedirects(
            response, reverse('getStudentInfo'), fetch_redirect_response=False
        )
        invoice_id = self.client.session[REG_VALIDATION_STR].get('invoice_id')
        self.assertIsNotNone(invoice_id)
        invoice = Invoice.objects.get(id=invoice_id)
        self.assertEqual(invoice.grossTotal, self.series.getBasePrice())

    def test_checkout_creates_registration_with_event_registration(self):
        self._cart_post(
            items=[{'item_type': 'Event', 'item_id': self.series.id,
                    'sku': self._general_sku(), 'quantity': 1}],
            checkout=True,
        )
        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR]['invoice_id']
        )
        reg = Registration.objects.filter(invoice=invoice).first()
        self.assertIsNotNone(reg)
        self.assertTrue(reg.eventregistration_set.filter(event=self.series).exists())
        self.assertFalse(reg.final)

    def test_checkout_stores_invoice_expiry_in_session(self):
        self._cart_post(
            items=[{'item_type': 'Event', 'item_id': self.series.id,
                    'sku': self._general_sku(), 'quantity': 1}],
            checkout=True,
        )
        self.assertIn(
            'invoice_expiry',
            self.client.session.get(REG_VALIDATION_STR, {})
        )

    def test_discount_code_stored_in_invoice_data(self):
        self._cart_post(
            items=[{'item_type': 'Event', 'item_id': self.series.id,
                    'sku': self._general_sku(), 'quantity': 1}],
            checkout=True,
            extra={'discount_code': 'TESTCODE'},
        )
        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR]['invoice_id']
        )
        self.assertEqual(invoice.data.get('discount_code'), 'TESTCODE')

    def test_full_checkout_flow_reaches_summary(self):
        '''Cart checkout -> student info -> registration summary.'''
        self._cart_post(
            items=[{'item_type': 'Event', 'item_id': self.series.id,
                    'sku': self._general_sku(), 'quantity': 1}],
            checkout=True,
        )
        response = self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Cart',
            'lastName': 'Tester',
            'email': 'cart@test.com',
            'agreeToPolicies': True,
        }, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        self.assertEqual(
            response.context_data['invoice'].grossTotal, self.series.getBasePrice()
        )

    # --- Variant handling ---

    def test_role_variant_accepted_in_cart(self):
        lead = self.defaultDanceRoles.get(name='Lead')
        er = EventRole.objects.create(event=self.series, role=lead, capacity=10)
        sku = f'EVENT_{self.series.id}_ROLE_{er.id}'
        response = self._cart_post([
            {'item_type': 'Event', 'item_id': self.series.id, 'sku': sku, 'quantity': 1}
        ])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['items'][0]['sku'], sku)

    def test_role_variant_creates_correct_event_registration(self):
        lead = self.defaultDanceRoles.get(name='Lead')
        EventRole.objects.create(event=self.series, role=lead, capacity=10)
        sku = f'EVENT_{self.series.id}_ROLE_{lead.id}'
        self._cart_post(
            items=[{'item_type': 'Event', 'item_id': self.series.id,
                    'sku': sku, 'quantity': 1}],
            checkout=True,
        )
        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR]['invoice_id']
        )
        reg = Registration.objects.filter(invoice=invoice).first()
        event_reg = reg.eventregistration_set.filter(event=self.series).first()
        self.assertIsNotNone(event_reg)
        self.assertEqual(event_reg.role, lead)

    # --- Drop-in ---

    def test_dropin_rejected_for_online_registration(self):
        response = self._cart_post([
            {'item_type': 'Event', 'item_id': self.series.id,
             'sku': self._general_sku(), 'quantity': 1, 'dropIn': True}
        ])
        self.assertEqual(response.status_code, 400)

    def test_dropin_accepted_at_door(self):
        self.series.allowDropins = True
        self.series.save()
        response = self._cart_post(
            items=[{'item_type': 'Event', 'item_id': self.series.id,
                    'sku': self._general_sku(), 'quantity': 1, 'dropIn': True}],
            as_door=True,
        )
        self.assertEqual(response.status_code, 200)

    # --- Door permissions ---

    def test_door_registration_rejected_without_permission(self):
        self.client.force_login(self.nonStaffUser)
        response = self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{'item_type': 'Event', 'item_id': self.series.id,
                           'sku': self._general_sku(), 'quantity': 1}],
                'checkout': False,
                'payAtDoor': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)


class CartSummaryViewTest(DefaultSchoolTestCase):
    '''
    Tests for CartSummaryView (/cart/summary/).  These tests cover the basic
    page rendering and the item-removal POST action.  Discount and voucher
    preview behaviour is tested in the discounts and vouchers apps respectively.
    '''

    def _set_session_cart(self, items, discount_code=None, payAtDoor=False):
        '''Helper: write a cart directly into the test session.'''
        cart = {'items': items, 'payAtDoor': payAtDoor}
        if discount_code:
            cart['discount_code'] = discount_code
        session = self.client.session
        session[REG_VALIDATION_STR] = {'cart': cart, 'payAtDoor': payAtDoor}
        session.save()

    def test_empty_cart_renders(self):
        '''CartSummaryView renders even when the session cart is empty.'''
        self._set_session_cart([])
        response = self.client.get(reverse('cartSummary'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context_data['cart_items'], [])
        self.assertEqual(response.context_data['gross_total'], 0)

    def test_event_item_shown_in_summary(self):
        '''An event added to the session cart appears in cart_items with the expected fields.'''
        series = self.create_series()
        sku = f'EVENT_{series.id}_GENERAL'
        self._set_session_cart([
            {'item_type': 'Event', 'item_id': series.id, 'sku': sku, 'quantity': 1}
        ])

        response = self.client.get(reverse('cartSummary'))

        self.assertEqual(response.status_code, 200)
        cart_items = response.context_data['cart_items']
        self.assertEqual(len(cart_items), 1)
        item = cart_items[0]
        self.assertEqual(item['item_id'], series.id)
        self.assertEqual(item['event'], series)
        self.assertAlmostEqual(item['price'], series.getBasePrice(payAtDoor=False))
        self.assertFalse(item['is_dropin'])
        # No _ROLE_ in sku, so role should not be set
        self.assertNotIn('role', item)

    def test_multiple_items_shown(self):
        '''Multiple events in the session cart each appear in cart_items.'''
        s1 = self.create_series()
        s2 = self.create_series(classDescription=self.levelTwoClassDescription)
        self._set_session_cart([
            {'item_type': 'Event', 'item_id': s1.id, 'sku': f'EVENT_{s1.id}_GENERAL', 'quantity': 1},
            {'item_type': 'Event', 'item_id': s2.id, 'sku': f'EVENT_{s2.id}_GENERAL', 'quantity': 1},
        ])

        response = self.client.get(reverse('cartSummary'))

        self.assertEqual(response.status_code, 200)
        cart_items = response.context_data['cart_items']
        self.assertEqual(len(cart_items), 2)
        item_ids = {item['item_id'] for item in cart_items}
        self.assertEqual(item_ids, {s1.id, s2.id})

    def test_gross_total_reflects_item_prices(self):
        '''gross_total in context equals sum of (price × quantity) across all items.'''
        series = self.create_series()
        self._set_session_cart([
            {'item_type': 'Event', 'item_id': series.id,
             'sku': f'EVENT_{series.id}_GENERAL', 'quantity': 2}
        ])

        response = self.client.get(reverse('cartSummary'))

        expected = series.getBasePrice(payAtDoor=False) * 2
        self.assertAlmostEqual(response.context_data['gross_total'], expected)

    def test_remove_item_updates_session(self):
        '''POSTing action=remove removes the targeted item from the session cart.'''
        series = self.create_series()
        sku = f'EVENT_{series.id}_GENERAL'
        self._set_session_cart([
            {'item_type': 'Event', 'item_id': series.id, 'sku': sku, 'quantity': 1}
        ])

        response = self.client.post(
            reverse('cartSummary'),
            data={'action': 'remove', 'item_id': str(series.id)},
        )

        self.assertRedirects(response, reverse('cartSummary'), fetch_redirect_response=False)
        updated_items = self.client.session[REG_VALIDATION_STR]['cart']['items']
        self.assertEqual(updated_items, [])

    def test_remove_one_of_two_items(self):
        '''Removing one item leaves the other intact in the session.'''
        s1 = self.create_series()
        s2 = self.create_series(classDescription=self.levelTwoClassDescription)
        self._set_session_cart([
            {'item_type': 'Event', 'item_id': s1.id, 'sku': f'EVENT_{s1.id}_GENERAL', 'quantity': 1},
            {'item_type': 'Event', 'item_id': s2.id, 'sku': f'EVENT_{s2.id}_GENERAL', 'quantity': 1},
        ])

        self.client.post(
            reverse('cartSummary'),
            data={'action': 'remove', 'item_id': str(s1.id)},
        )

        remaining = self.client.session[REG_VALIDATION_STR]['cart']['items']
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]['item_id'], s2.id)

    def test_unknown_action_is_safe(self):
        '''An unrecognised POST action redirects back without modifying the cart.'''
        series = self.create_series()
        sku = f'EVENT_{series.id}_GENERAL'
        self._set_session_cart([
            {'item_type': 'Event', 'item_id': series.id, 'sku': sku, 'quantity': 1}
        ])

        response = self.client.post(
            reverse('cartSummary'),
            data={'action': 'bogus'},
        )

        self.assertRedirects(response, reverse('cartSummary'), fetch_redirect_response=False)
        items = self.client.session[REG_VALIDATION_STR]['cart']['items']
        self.assertEqual(len(items), 1)

    # --- action=add tests ---------------------------------------------------

    def test_add_item_to_empty_cart(self):
        '''POSTing action=add to an empty session creates the cart and adds the item.'''
        series = self.create_series()
        sku = f'EVENT_{series.id}_GENERAL'

        response = self.client.post(reverse('cartSummary'), data={
            'action': 'add',
            'item_id': str(series.id),
            'sku': sku,
            'quantity': '1',
        })

        self.assertRedirects(response, reverse('cartSummary'), fetch_redirect_response=False)
        items = self.client.session[REG_VALIDATION_STR]['cart']['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['item_id'], series.id)
        self.assertEqual(items[0]['sku'], sku)
        self.assertEqual(items[0]['quantity'], 1)
        self.assertEqual(items[0]['item_type'], 'Event')

    def test_add_item_to_existing_cart(self):
        '''POSTing action=add appends to a cart that already contains items.'''
        s1 = self.create_series()
        s2 = self.create_series(classDescription=self.levelTwoClassDescription)
        self._set_session_cart([
            {'item_type': 'Event', 'item_id': s1.id,
             'sku': f'EVENT_{s1.id}_GENERAL', 'quantity': 1},
        ])

        self.client.post(reverse('cartSummary'), data={
            'action': 'add',
            'item_id': str(s2.id),
            'sku': f'EVENT_{s2.id}_GENERAL',
            'quantity': '1',
        })

        items = self.client.session[REG_VALIDATION_STR]['cart']['items']
        self.assertEqual(len(items), 2)
        item_ids = {i['item_id'] for i in items}
        self.assertEqual(item_ids, {s1.id, s2.id})

    def test_add_item_with_role(self):
        '''action=add stores the role-bearing SKU and item_type correctly.'''
        series = self.create_series()
        lead_role = self.defaultDanceRoles.get(name='Lead')
        sku = f'EVENT_{series.id}_ROLE_{lead_role.id}'

        self.client.post(reverse('cartSummary'), data={
            'action': 'add',
            'item_id': str(series.id),
            'sku': sku,
            'quantity': '1',
        })

        items = self.client.session[REG_VALIDATION_STR]['cart']['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['sku'], sku)

    def test_add_dropin_item(self):
        '''action=add with dropIn=true stores the dropIn and dropInOccurrence fields.'''
        series = self.create_series()
        occurrence = series.eventoccurrence_set.first()
        sku = f'EVENT_{series.id}_DROPIN_GENERAL'

        self.client.post(reverse('cartSummary'), data={
            'action': 'add',
            'item_id': str(series.id),
            'sku': sku,
            'quantity': '1',
            'dropIn': 'true',
            'dropInOccurrence': str(occurrence.id),
        })

        items = self.client.session[REG_VALIDATION_STR]['cart']['items']
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].get('dropIn'))
        self.assertEqual(items[0].get('dropInOccurrence'), occurrence.id)

    def test_add_item_missing_id_shows_error(self):
        '''action=add with no item_id redirects back without modifying the cart.'''
        self._set_session_cart([])

        response = self.client.post(reverse('cartSummary'), data={
            'action': 'add',
            'item_id': 'notanumber',
            'sku': 'EVENT_0_GENERAL',
        })

        self.assertRedirects(response, reverse('cartSummary'), fetch_redirect_response=False)
        items = self.client.session[REG_VALIDATION_STR]['cart']['items']
        self.assertEqual(items, [])

    def test_add_item_falls_back_to_general_sku(self):
        '''action=add with no sku posted defaults to EVENT_{id}_GENERAL.'''
        series = self.create_series()

        self.client.post(reverse('cartSummary'), data={
            'action': 'add',
            'item_id': str(series.id),
            'quantity': '1',
        })

        items = self.client.session[REG_VALIDATION_STR]['cart']['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['sku'], f'EVENT_{series.id}_GENERAL')


class EventAddOnChildGrossTotalTest(DefaultSchoolTestCase):
    '''
    Reproduces an inconsistency in core/handlers.py:linkCartEventRegistration
    where InvoiceItems created for EventAddOn children get grossTotal set
    to the child event's standalone base price (line 303) instead of the
    parent's allocated share for that child (which getAllocatedTotals
    correctly computes and is used for the parent's own grossTotal at
    line 306-309).

    Item.total is currently corrected via _initial_total fallback at
    line 313, so the invoice grand total still lands right. But
    sum(item.grossTotal) > parent.getBasePrice() whenever any add-on's
    allocated share differs from its own base price, leaving per-item
    breakdowns misleading and the grossTotal column out of sync with
    total in financial reports.
    '''

    @unittest.expectedFailure
    def test_addon_child_grosstotal_matches_allocated_share(self):
        # Three tiers with prices that force a non-trivial residual
        # allocation: parent ($50) is cheaper than the children together
        # ($30 + $60 = $90), so the allocation produces shares ≠ base prices.
        parent_tier = PricingTier.objects.create(
            name='Parent Tier', onlinePrice=50, doorPrice=50, dropinPrice=50,
        )
        child1_tier = PricingTier.objects.create(
            name='Child 1 Tier', onlinePrice=30, doorPrice=30, dropinPrice=30,
        )
        child2_tier = PricingTier.objects.create(
            name='Child 2 Tier', onlinePrice=60, doorPrice=60, dropinPrice=60,
        )

        parent = self.create_series(pricingTier=parent_tier)
        child1 = self.create_series(pricingTier=child1_tier)
        child2 = self.create_series(pricingTier=child2_tier)

        EventAddOn.objects.create(
            event=parent, addOnEvent=child1, order=1,
            allocationType=EventAddOn.AllocationType.residual,
        )
        EventAddOn.objects.create(
            event=parent, addOnEvent=child2, order=2,
            allocationType=EventAddOn.AllocationType.residual,
        )

        sku = f'EVENT_{parent.id}_GENERAL'
        response = self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{'item_type': 'Event', 'item_id': parent.id,
                           'sku': sku, 'quantity': 1}],
                'checkout': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)

        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR].get('invoice_id')
        )
        total_gross = sum(it.grossTotal for it in invoice.invoiceitem_set.all())

        # Sum of per-item grossTotal must equal what the customer is
        # actually being asked to pay for the parent registration.
        # With the bug: parent=0, child1=$30, child2=$60 → sum=$90 (not $50).
        self.assertAlmostEqual(
            total_gross, parent.getBasePrice(), places=2,
            msg=(
                'Sum of InvoiceItem.grossTotal ({0}) does not match '
                'parent.getBasePrice() ({1}). Children use their own '
                'base price instead of their allocated share '
                '(handlers.py:303 vs getAllocatedTotals at line 268).'
            ).format(total_gross, parent.getBasePrice()),
        )
