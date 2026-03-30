"""
Tests for danceschool.register.

Split into three sections:

1. RegisterRenderTest  — uses Django's test client to verify server-side HTML
   (no browser required, runs as part of the normal test suite).

2. RegisterCartTest    — uses Playwright to drive a real browser and verify
   that cart interactions (add, remove, total display) work end-to-end.

3. PublicRegisterReferralTest — verifies the voucher_id and marketing_id
   referral URL patterns on PublicRegisterView (no browser required).

Dependencies for the browser tests:
    pip install playwright
    playwright install chromium
    playwright install-deps   # installs OS-level libraries for headless Chrome
"""

import json
import re
import unittest
from datetime import timedelta
from urllib.parse import urlparse

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from django.utils import timezone

from cms.api import add_plugin

from dynamic_preferences.registries import global_preferences_registry

from danceschool.core.constants import getConstant, REG_VALIDATION_STR, updateConstant
from danceschool.core.models import (
    Invoice,
    DanceRole, DanceType, DanceTypeLevel, ClassDescription, PricingTier,
    Location, StaffMember, Instructor, Event, Series, PublicEvent,
    EventStaffMember, EventOccurrence,
)
from danceschool.core.utils.tests import DefaultSchoolTestCase

from .models import Register

try:
    from playwright.sync_api import sync_playwright, expect as pw_expect
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


# ---------------------------------------------------------------------------
# 1. Server-side rendering tests (no browser)
# ---------------------------------------------------------------------------

class RegisterRenderTest(DefaultSchoolTestCase):
    """
    Verify that the at-the-door register page renders correctly.

    These tests use Django's test client so they run without a browser and
    are included in the main test suite.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.register = Register.objects.create(
            title='Test Register',
            slug='test-register',
            enabled=True,
        )
        # add_plugin creates the RegisterEventPluginModel; its save() method
        # auto-generates one default RegisterEventPluginChoice (by role).
        # occursWithinDays=None removes the "must occur today" filter so any
        # open series shows up regardless of when its occurrences fall.
        cls.plugin = add_plugin(cls.register.placeholder, 'RegisterEventPlugin', 'en')
        cls.plugin.occursWithinDays = None
        cls.plugin.save()

    def _url(self):
        return reverse('registerView', kwargs={'slug': 'test-register'})

    def _open_series(self, **kwargs):
        """
        Convenience wrapper around create_series that defaults to a start
        time two hours from now so the series is always open for registration.
        """
        kwargs.setdefault('startTime', timezone.now() + timedelta(hours=2))
        return self.create_series(**kwargs)

    # -- Access control -------------------------------------------------------

    def test_anonymous_user_is_redirected(self):
        """Unauthenticated users must not see the register page."""
        response = self.client.get(self._url())
        self.assertIn(response.status_code, [302, 403])

    def test_unprivileged_user_cannot_access(self):
        """A logged-in user without door-payment permission must be denied."""
        self.client.force_login(self.nonStaffUser)
        response = self.client.get(self._url())
        self.assertIn(response.status_code, [302, 403])

    def test_superuser_gets_200(self):
        """A superuser (all permissions) must be able to load the register page."""
        self.client.force_login(self.superuser)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    # -- Content -------------------------------------------------------------

    def test_register_title_in_response(self):
        """The register title must appear in the rendered HTML."""
        self.client.force_login(self.superuser)
        response = self.client.get(self._url())
        self.assertContains(response, 'Test Register')

    def test_open_series_shows_add_item_buttons(self):
        """
        A Series that is open for registration must produce at least one
        .add-item button on the register page.
        """
        self.client.force_login(self.superuser)
        self._open_series()
        response = self.client.get(self._url())
        self.assertContains(response, 'add-item')

    def test_closed_series_produces_no_buttons(self):
        """
        A Series whose registration is closed must not produce .add-item
        buttons (the plugin default filters for open events only).
        """
        self.client.force_login(self.superuser)
        # status=disabled means registrationOpen will be False.
        self._open_series(status=Event.RegStatus.disabled)
        response = self.client.get(self._url())
        self.assertNotContains(response, 'add-item')

    def test_event_name_appears_in_response(self):
        """The class description title must appear on the page."""
        self.client.force_login(self.superuser)
        self._open_series()
        response = self.client.get(self._url())
        self.assertContains(response, self.levelOneClassDescription.title)

    def test_door_price_in_response(self):
        """
        The door price from defaultPricing (60) must appear somewhere on the
        page so the cashier can confirm it.
        """
        self.client.force_login(self.superuser)
        self._open_series()
        response = self.client.get(self._url())
        self.assertContains(response, '60')

    def test_disabled_register_returns_404(self):
        """A Register with enabled=False must return 404."""
        Register.objects.create(title='Disabled', slug='disabled', enabled=False)
        self.client.force_login(self.superuser)
        url = reverse('registerView', kwargs={'slug': 'disabled'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# 2. Browser / cart interaction tests (Playwright)
# ---------------------------------------------------------------------------

@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, 'playwright is not installed — run: pip install playwright && playwright install chromium')
class RegisterCartTest(StaticLiveServerTestCase):
    """
    End-to-end browser tests for the at-the-door shopping cart.

    These tests launch a real headless browser (Chromium via Playwright) and
    verify that JavaScript cart interactions — adding items, removing them,
    price display — work correctly against the CartView API.

    Run only these tests:
        python manage.py test danceschool.register.tests.RegisterCartTest

    Required one-time setup (only needed once per machine):
        pip install playwright
        playwright install chromium
        playwright install-deps   # Linux only: system libraries for Chromium
    """

    # -- Playwright lifecycle (browser starts once per class) -----------------

    @classmethod
    def setUpClass(cls):
        # Playwright's sync API runs an asyncio event loop inside a greenlet
        # dispatcher (loop.run_until_complete in a greenlet, then yields back).
        # While any sync_playwright() handle is live, asyncio.get_event_loop()
        # .is_running() returns True, which triggers Django's async_unsafe guard
        # on every ORM call.  Setting this env variable disables that guard for
        # the lifetime of this test class only.
        import os
        cls._async_unsafe_original = os.environ.get('DJANGO_ALLOW_ASYNC_UNSAFE')
        os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
        super().setUpClass()
        cls._pw = sync_playwright().start()
        cls.browser = cls._pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pw.stop()
        super().tearDownClass()
        import os
        if cls._async_unsafe_original is None:
            os.environ.pop('DJANGO_ALLOW_ASYNC_UNSAFE', None)
        else:
            os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = cls._async_unsafe_original

    # -- Per-test setup -------------------------------------------------------
    # LiveServerTestCase extends TransactionTestCase, which flushes the DB
    # before every individual test.  All DB fixtures must therefore be created
    # in setUp(), not setUpTestData().

    def setUp(self):
        super().setUp()
        self._setup_school_data()
        self._setup_register()
        # A fresh browser context per test gives clean cookies/storage.
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self._inject_session()

    def tearDown(self):
        self.context.close()
        super().tearDown()

    # -- Data helpers ---------------------------------------------------------

    def _setup_school_data(self):
        """Re-create the baseline school fixtures needed for all tests."""
        from dynamic_preferences.registries import global_preferences_registry
        gp = global_preferences_registry.manager()
        gp.load_from_db()

        DanceRole.objects.create(name='Lead', order=1)
        DanceRole.objects.create(name='Follow', order=2)
        dance_roles = DanceRole.objects.filter(name__in=['Lead', 'Follow'])

        dance_type = DanceType.objects.create(name='Lindy Hop', order=1)
        dance_type.roles.set(dance_roles)

        level = DanceTypeLevel.objects.create(
            name='Level 1', order=1, danceType=dance_type
        )
        self.levelOneClassDescription = ClassDescription.objects.create(
            title='Test Level One Class',
            description='A test class.',
            danceTypeLevel=level,
            slug='test-level-one',
        )
        self.defaultPricing = PricingTier.objects.create(
            name='Default Pricing',
            onlinePrice=50,
            doorPrice=60,
            dropinPrice=10,
        )
        self.defaultLocation = Location.objects.create(
            name='Default Location',
            status=Location.StatusChoices.active,
            address='123 Test Street',
            city='Boston',
            state='MA',
            zip='02114',
            defaultCapacity=50,
        )
        self.superuser = User.objects.create_superuser(
            'admin', 'admin@test.com', 'pass'
        )
        staff_member = StaffMember.objects.create(
            firstName='Frankie',
            lastName='Manning',
            userAccount=self.superuser,
            publicEmail='admin@test.com',
            privateEmail='admin@test.com',
        )
        Instructor.objects.create(
            staffMember=staff_member,
            status=Instructor.InstructorStatus.roster,
        )
        self.defaultInstructor = staff_member

    def _setup_register(self):
        """Create the Register page and its RegisterEventPlugin."""
        self.register = Register.objects.create(
            title='Test Register',
            slug='test-register',
            enabled=True,
        )
        self.plugin = add_plugin(
            self.register.placeholder, 'RegisterEventPlugin', 'en'
        )
        # Removing the occurrence-date filter makes timing in tests predictable:
        # any series that is open for registration will be listed.
        self.plugin.occursWithinDays = None
        self.plugin.save()

    def create_series(self, **kwargs):
        """
        Create a Series open for registration.  Defaults to starting two
        hours from now so it is never accidentally in the past.
        """
        start = kwargs.pop('startTime', timezone.now() + timedelta(hours=2))
        s = Series(
            classDescription=kwargs.pop(
                'classDescription', self.levelOneClassDescription
            ),
            pricingTier=kwargs.pop('pricingTier', self.defaultPricing),
            location=kwargs.pop('location', self.defaultLocation),
            status=kwargs.pop('status', Event.RegStatus.enabled),
        )
        s.save()
        EventOccurrence.objects.create(
            event=s,
            startTime=start,
            endTime=start + timedelta(hours=1),
        )
        staff = EventStaffMember.objects.create(
            event=s,
            category=getConstant('general__eventStaffCategoryInstructor'),
            staffMember=self.defaultInstructor,
        )
        staff.occurrences.set(s.eventoccurrence_set.all())
        s.save()
        return s

    # -- Browser helpers ------------------------------------------------------

    def _inject_session(self):
        """
        Authenticate the Playwright browser as the Django superuser by
        injecting the session cookie that force_login() created.

        This avoids automating the login form and is safe because the test
        client and the live server share the same database.
        """
        self.client.force_login(self.superuser)
        session_key = self.client.session.session_key
        domain = urlparse(self.live_server_url).hostname
        self.context.add_cookies([{
            'name': 'sessionid',
            'value': session_key,
            'domain': domain,
            'path': '/',
        }])

    def _register_url(self):
        return self.live_server_url + reverse(
            'registerView', kwargs={'slug': 'test-register'}
        )

    def _load_page_with_series(self):
        """
        Create an open series, navigate to the register page, and wait for
        both the .add-item buttons AND the JS catalog initialization to finish
        before returning.  The catalog fetch (PurchasableItemsView) must
        complete before the first add-item click so that lookupPrice() returns
        the correct door price instead of 0.
        """
        self.create_series()
        self.page.goto(self._register_url())
        self.page.wait_for_selector('.add-item', state='visible', timeout=10_000)
        # networkidle = no pending XHR/fetch for ≥500 ms, meaning both the
        # purchasableItems fetch and the cart GET have finished.
        self.page.wait_for_load_state('networkidle', timeout=10_000)

    def _expand_cart(self):
        """
        Make the Bootstrap-collapsed cart container visible so that buttons
        inside it (#emptyCart, .remove-item) can be clicked.
        """
        self.page.evaluate(
            "document.getElementById('cart-container').style.display = 'block'"
        )

    # -- Tests ----------------------------------------------------------------

    def test_page_loads_with_register_title(self):
        """The register title must be visible after the page loads."""
        self.create_series()
        self.page.goto(self._register_url())
        pw_expect(self.page.locator('h1')).to_contain_text('Test Register')

    def test_add_item_button_visible_for_open_series(self):
        """At least one .add-item button must be present for an open series."""
        self._load_page_with_series()
        pw_expect(self.page.locator('.add-item').first).to_be_visible()

    def test_cart_submit_hidden_when_cart_empty(self):
        """The checkout button must be invisible before any items are added."""
        self.create_series()
        self.page.goto(self._register_url())
        # Wait for the JS catalogue fetch to complete.
        self.page.wait_for_load_state('networkidle', timeout=10_000)
        pw_expect(self.page.locator('#cart-submit')).to_have_class(
            re.compile(r'\binvisible\b')
        )

    def test_add_item_populates_cart_row(self):
        """
        Clicking an .add-item button must add exactly one row to the
        #cartItems table.
        """
        self._load_page_with_series()
        self.page.locator('.add-item').first.click()
        pw_expect(self.page.locator('#cartItems tr')).to_have_count(
            1, timeout=8_000
        )

    def test_cart_total_shows_door_price(self):
        """
        After adding one event the cart total must equal the door price
        (60.00 from defaultPricing).
        """
        self._load_page_with_series()
        self.page.locator('.add-item').first.click()
        pw_expect(self.page.locator('#cartTotal')).to_have_text(
            re.compile(r'60\.00'), timeout=8_000
        )

    def test_cart_submit_becomes_visible_after_add(self):
        """
        The checkout button must lose its 'invisible' class once an item is
        in the cart.
        """
        self._load_page_with_series()
        self.page.locator('.add-item').first.click()
        pw_expect(self.page.locator('#cart-submit')).not_to_have_class(
            re.compile(r'\binvisible\b'), timeout=8_000
        )

    def test_remove_item_clears_cart(self):
        """
        After adding then removing an item the cart must be empty and the
        checkout button must return to invisible.
        """
        self._load_page_with_series()
        self.page.locator('.add-item').first.click()
        pw_expect(self.page.locator('#cartItems tr')).to_have_count(
            1, timeout=8_000
        )
        # The remove button lives inside the Bootstrap-collapsed #cart-container.
        self._expand_cart()
        self.page.locator('.remove-item').first.click()
        pw_expect(self.page.locator('#cartItems tr')).to_have_count(
            0, timeout=8_000
        )
        pw_expect(self.page.locator('#cart-submit')).to_have_class(
            re.compile(r'\binvisible\b'), timeout=5_000
        )

    def test_empty_cart_button_clears_all_items(self):
        """The 'Empty Cart' button must remove all items at once."""
        self._load_page_with_series()
        self.page.locator('.add-item').first.click()
        pw_expect(self.page.locator('#cartItems tr')).to_have_count(
            1, timeout=8_000
        )
        # #emptyCart lives inside the Bootstrap-collapsed #cart-container.
        self._expand_cart()
        self.page.locator('#emptyCart').click()
        pw_expect(self.page.locator('#cartItems tr')).to_have_count(
            0, timeout=8_000
        )

    def test_badge_counter_increments_after_add(self):
        """
        The badge counter on the clicked .add-item button must show '1' after
        a successful add.
        """
        self._load_page_with_series()
        self.page.locator('.add-item').first.click()
        pw_expect(
            self.page.locator('.badge-choice-counter').first
        ).to_have_text('1', timeout=8_000)


# ---------------------------------------------------------------------------
# 3. PublicRegisterView server-side rendering tests (no browser)
# ---------------------------------------------------------------------------

class PublicRegisterRenderTest(DefaultSchoolTestCase):
    """
    Verify that the public-facing registration page renders correctly.

    The setup replicates the default three-plugin layout produced by
    setup_public_register: an open-series section, an open-public-events
    section, and a closed/ongoing-series section.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        from django.contrib.sites.models import Site
        from danceschool.core.management.commands.migrate_static_placeholders import (
            _get_or_create_alias_category,
            _get_or_create_alias,
            _get_or_create_alias_content,
        )

        site = Site.objects.get_current()
        cat = _get_or_create_alias_category()
        alias = _get_or_create_alias(cat, 'public_register_content', site)
        alias_content = _get_or_create_alias_content(
            alias, 'public_register_content', 'en', cls.superuser
        )
        placeholder = alias_content.placeholder

        add_plugin(placeholder, 'PublicRegisterNavPlugin', 'en')

        cls.open_series_plugin = add_plugin(
            placeholder, 'PublicRegisterEventPlugin', 'en',
            title='Upcoming Classes',
            eventType='S',
            registrationOpenLimit='O',
            occursWithinDays=None,
        )
        cls.open_events_plugin = add_plugin(
            placeholder, 'PublicRegisterEventPlugin', 'en',
            title='Upcoming Events',
            eventType='P',
            registrationOpenLimit='O',
            occursWithinDays=None,
        )
        cls.closed_series_plugin = add_plugin(
            placeholder, 'PublicRegisterEventPlugin', 'en',
            title='Ongoing Classes',
            eventType='S',
            registrationOpenLimit='C',
            occursWithinDays=None,
        )

    def _url(self):
        return reverse('publicRegistration')

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
        self.create_series(status=Event.RegStatus.disabled)
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
        from .models import PublicRegisterEventPluginChoice
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


# ---------------------------------------------------------------------------
# 4. PublicRegisterView referral URL tests (no browser)
# ---------------------------------------------------------------------------

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
            reverse('publicRegistrationWithVoucher', kwargs={'voucher_id': v.voucherId})
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
            reverse('publicRegistrationWithVoucher', kwargs={'voucher_id': 'DOESNOTEXIST'})
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
            reverse('publicRegistrationWithVoucher', kwargs={'voucher_id': v.voucherId})
        )

        cart_response = self.client.get(reverse('cart'))
        self.assertEqual(cart_response.status_code, 200)
        self.assertEqual(
            json.loads(cart_response.content).get('discount_code'), v.voucherId
        )

    def test_voucher_url_reduces_checkout_price(self):
        """
        Full referral-URL flow: visiting publicRegistrationWithVoucher
        pre-populates discount_code in the session cart, the frontend JS reads
        it back via GET /cart/ and forwards it when submitting, and the
        outstanding balance is reduced by the voucher amount after checkout.

        Steps:
        1. Visit publicRegistrationWithVoucher → discount_code stored in session.
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
            reverse('publicRegistrationWithVoucher', kwargs={'voucher_id': v.voucherId})
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
            reverse('publicRegistrationWithMarketingId',
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
            reverse('publicRegistrationWithMarketingId',
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
