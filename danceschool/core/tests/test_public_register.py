import json

from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from dynamic_preferences.registries import global_preferences_registry

from ..models import EventOccurrence, Event, Series, PublicEvent, Invoice
from ..constants import updateConstant, REG_VALIDATION_STR
from .defaults import DefaultSchoolTestCase


class PublicRegisterRenderTest(DefaultSchoolTestCase):
    """
    Verify that the public-facing registration page renders correctly.

    The setup replicates the default three-plugin layout produced by
    setup_public_register: an open-series section, an open-public-events
    section, and a closed/ongoing-series section.
    """

    def _url(self):
        return reverse('registration')

    def _open_series(self, **kwargs):
        kwargs.setdefault('startTime', timezone.now() + timedelta(hours=2))
        return self.create_series(**kwargs)

    def _open_public_event(self):
        start = timezone.now() + timedelta(hours=2)
        pe = PublicEvent(
            title='Test Public Event',
            slug='test-public-event',
            pricingTier=self.defaultPricing,
            location=self.defaultLocation,
            status=Event.RegStatus.enabled,
        )
        pe.save()
        EventOccurrence.objects.create(
            event=pe,
            startTime=start,
            endTime=start + timedelta(hours=1),
        )
        pe.save()
        return pe

    # -- Access control -------------------------------------------------------

    def test_anonymous_user_can_access(self):
        """The public register page must be accessible without login."""
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_registration_offline_redirects_public(self):
        """When registration is disabled, anonymous users must be sent to the offline page."""
        gp = global_preferences_registry.manager()
        gp['registration__registrationEnabled'] = False
        try:
            response = self.client.get(self._url())
            self.assertRedirects(
                response,
                reverse('registrationOffline'),
                fetch_redirect_response=False,
            )
        finally:
            gp['registration__registrationEnabled'] = True

    def test_registration_offline_staff_can_access(self):
        """Staff with accept_door_payments must still see the page when registration is disabled."""
        gp = global_preferences_registry.manager()
        gp['registration__registrationEnabled'] = False
        try:
            self.client.force_login(self.superuser)
            response = self.client.get(self._url())
            self.assertEqual(response.status_code, 200)
        finally:
            gp['registration__registrationEnabled'] = True

    # -- Content --------------------------------------------------------------

    def test_open_series_appears_with_quantity_inputs(self):
        """A series open for registration must appear with quantity inputs."""
        self._open_series()
        response = self.client.get(self._url())
        self.assertContains(response, self.levelOneClassDescription.title)
        self.assertContains(response, 'register-quantity')

    def test_open_public_event_appears(self):
        """A public event open for registration must appear on the page."""
        self._open_public_event()
        response = self.client.get(self._url())
        self.assertContains(response, 'Test Public Event')

    def test_closed_series_appears(self):
        """A series closed for registration must appear in the ongoing-classes section."""
        # The closed-series plugin uses daysStart=0 / daysEnd=0, which limits
        # to events that have started (startTime <= now) but not yet ended
        # (endTime >= now).  Create a series whose single occurrence spans
        # from 1 hour ago to 1 hour from now with registration disabled.
        s = self.create_series(status=Event.RegStatus.disabled)
        occ = s.eventoccurrence_set.first()
        occ.startTime = timezone.now() - timedelta(hours=1)
        occ.endTime = timezone.now() + timedelta(hours=1)
        occ.save()
        s.save()
        response = self.client.get(self._url())
        self.assertContains(response, 'Ongoing Classes')
        self.assertContains(response, self.levelOneClassDescription.title)

    def test_open_series_absent_from_closed_section(self):
        """
        An open series must not appear in the closed/ongoing section.
        When only an open series exists the 'Ongoing Classes' section must
        contain no event cards.
        """
        self._open_series()
        response = self.client.get(self._url())
        # The section heading is rendered regardless of whether it has events;
        # verify that the class description title does NOT appear after
        # 'Ongoing Classes' in the response.
        content = response.content.decode()
        ongoing_idx = content.find('Ongoing Classes')
        self.assertNotEqual(ongoing_idx, -1, 'Ongoing Classes section missing')
        tail = content[ongoing_idx:]
        self.assertNotIn(self.levelOneClassDescription.title, tail)

    # -- Sold-out behaviour ---------------------------------------------------

    def test_sold_out_badge_displayed(self):
        """A sold-out series must show the 'Sold out' badge."""
        s = self._open_series()
        # Use update() to bypass Event.save() which would restore capacity
        # from the location's defaultCapacity.  capacity=0 ensures
        # numRegistered (0) >= capacity (0) → soldOut is True.
        Series.objects.filter(pk=s.pk).update(capacity=0)
        response = self.client.get(self._url())
        self.assertContains(response, 'Sold out')

    def test_sold_out_choice_hidden_when_rule_is_hide(self):
        """When soldOutRule='H', sold-out choices must be absent from the page."""
        from danceschool.core.models import PublicRegisterEventPluginChoice
        PublicRegisterEventPluginChoice.objects.filter(
            eventPlugin=self.open_series_plugin
        ).update(soldOutRule='H')
        try:
            s = self._open_series()
            Series.objects.filter(pk=s.pk).update(capacity=0)
            response = self.client.get(self._url())
            self.assertNotContains(response, 'register-quantity')
            self.assertNotContains(response, 'Sold out')
        finally:
            PublicRegisterEventPluginChoice.objects.filter(
                eventPlugin=self.open_series_plugin
            ).update(soldOutRule='D')


class PublicRegisterReferralTest(PublicRegisterRenderTest):
    """
    Tests for voucher_id and marketing_id referral URL parameters on
    PublicRegisterView.

    Voucher codes passed via the URL are validated immediately: valid codes are
    stored in the session cart as discount_code (reducing the checkout price);
    invalid codes produce a warning message and are not stored.

    Marketing IDs are stored in the session and are written to invoice.data
    when the cart is checked out.
    """

    def create_voucher(self, **kwargs):
        from danceschool.vouchers.models import Voucher
        v = Voucher(
            voucherId=kwargs.get('voucherId', 'TEST_VOUCHER'),
            name=kwargs.get('name', 'Test Voucher'),
            originalAmount=kwargs.get('originalAmount', 10),
            maxAmountPerUse=kwargs.get('maxAmountPerUse', None),
            disabled=kwargs.get('disabled', False),
            expirationDate=kwargs.get('expirationDate', None),
            forPreviousCustomersOnly=kwargs.get('forPreviousCustomersOnly', False),
            forFirstTimeCustomersOnly=kwargs.get('forFirstTimeCustomersOnly', False),
        )
        v.save()
        return v

    # -- voucher_id tests ---------------------------------------------------

    def test_valid_voucher_url_stores_discount_code_in_session(self):
        """
        A valid voucher code in the URL is validated immediately and stored as
        discount_code in the session cart.
        """
        updateConstant('vouchers__enableVouchers', True)
        v = self.create_voucher(expirationDate=timezone.now() + timedelta(days=1))

        response = self.client.get(
            reverse('registrationWithVoucher', kwargs={'voucher_id': v.voucherId})
        )
        self.assertEqual(response.status_code, 200)

        session_cart = self.client.session.get(REG_VALIDATION_STR, {}).get('cart', {})
        self.assertEqual(session_cart.get('discount_code'), v.voucherId)

    def test_invalid_voucher_url_shows_warning_and_is_not_stored(self):
        """
        An unrecognised voucher code in the URL produces a warning message and
        is not written to the session cart.
        """
        updateConstant('vouchers__enableVouchers', True)

        response = self.client.get(
            reverse('registrationWithVoucher', kwargs={'voucher_id': 'DOESNOTEXIST'})
        )
        self.assertEqual(response.status_code, 200)

        messages_list = list(response.wsgi_request._messages)
        self.assertTrue(
            any('DOESNOTEXIST' in str(m) for m in messages_list),
            'Expected a warning message containing the invalid voucher code',
        )
        session_cart = self.client.session.get(REG_VALIDATION_STR, {}).get('cart', {})
        self.assertIsNone(session_cart.get('discount_code'))

    def test_voucher_url_cart_get_returns_discount_code(self):
        """
        After visiting the voucher referral URL, GET /cart/ returns the
        pre-populated discount_code so the frontend JS can include it in
        subsequent cart POSTs.
        """
        updateConstant('vouchers__enableVouchers', True)
        v = self.create_voucher(expirationDate=timezone.now() + timedelta(days=1))

        self.client.get(
            reverse('registrationWithVoucher', kwargs={'voucher_id': v.voucherId})
        )

        cart_response = self.client.get(reverse('cart'))
        self.assertEqual(cart_response.status_code, 200)
        self.assertEqual(
            json.loads(cart_response.content).get('discount_code'), v.voucherId
        )

    def test_voucher_url_reduces_checkout_price(self):
        """
        Full referral-URL flow: visiting registrationWithVoucher
        pre-populates discount_code in the session cart, the frontend JS reads
        it back via GET /cart/ and forwards it when submitting, and the
        outstanding balance is reduced by the voucher amount after checkout.

        Steps:
        1. Visit registrationWithVoucher → discount_code stored in session.
        2. GET /cart/ → retrieve discount_code (simulates what the JS does).
        3. POST items + discount_code + checkout=True to CartView.
        4. POST to StudentInfoView to complete registration.
        5. Verify outstanding balance is reduced by the voucher's originalAmount.
        """
        updateConstant('vouchers__enableVouchers', True)
        s = self._open_series()
        v = self.create_voucher(
            originalAmount=10,
            expirationDate=timezone.now() + timedelta(days=1),
        )

        # Step 1
        self.client.get(
            reverse('registrationWithVoucher', kwargs={'voucher_id': v.voucherId})
        )

        # Step 2
        prefilled_code = json.loads(
            self.client.get(reverse('cart')).content
        ).get('discount_code')
        self.assertEqual(prefilled_code, v.voucherId)

        # Step 3
        sku = f'EVENT_{s.id}_GENERAL'
        response = self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{'item_type': 'Event', 'item_id': s.id,
                           'sku': sku, 'quantity': 1}],
                'discount_code': prefilled_code,
                'checkout': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)

        # Step 4
        response = self.client.post(
            reverse('getStudentInfo'),
            {
                'firstName': 'Referral',
                'lastName': 'Customer',
                'email': 'referral@test.com',
                'agreeToPolicies': True,
            },
            follow=True,
        )

        # Step 5
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])
        invoice = response.context_data.get('invoice')
        self.assertEqual(
            invoice.outstandingBalance,
            s.getBasePrice() - v.originalAmount,
        )

    # -- marketing_id tests -------------------------------------------------

    def test_marketing_id_url_stores_in_session(self):
        """
        Visiting the marketing ID URL stores marketing_id in the session so
        that create_invoice_from_cart can later write it to invoice.data.
        """
        marketing_id = 'SUMMER2024'

        response = self.client.get(
            reverse('registrationWithMarketingId',
                    kwargs={'marketing_id': marketing_id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.session.get(REG_VALIDATION_STR, {}).get('marketing_id'),
            marketing_id,
        )

    def test_marketing_id_flows_to_invoice_on_cart_submit(self):
        """
        After visiting the marketing ID URL, submitting the cart with
        checkout=True creates an invoice whose data dict contains marketing_id.
        """
        s = self._open_series()
        marketing_id = 'SUMMER2024'

        # Step 1: Prime the session with the marketing ID.
        self.client.get(
            reverse('registrationWithMarketingId',
                    kwargs={'marketing_id': marketing_id})
        )

        # Step 2: Submit the cart (no marketing_id in the POST body —
        # create_invoice_from_cart reads it from the session).
        sku = f'EVENT_{s.id}_GENERAL'
        response = self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{'item_type': 'Event', 'item_id': s.id,
                           'sku': sku, 'quantity': 1}],
                'checkout': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)

        # Step 3: Verify invoice.data has the marketing_id.
        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR]['invoice_id']
        )
        self.assertEqual(invoice.data.get('marketing_id'), marketing_id)
