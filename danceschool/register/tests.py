"""
Tests for danceschool.register.

Split into two sections:

1. RegisterRenderTest  — uses Django's test client to verify server-side HTML
   (no browser required, runs as part of the normal test suite).

2. RegisterCartTest    — uses Playwright to drive a real browser and verify
   that cart interactions (add, remove, total display) work end-to-end.

Dependencies for the browser tests:
    pip install playwright
    playwright install chromium
    playwright install-deps   # installs OS-level libraries for headless Chrome
"""

import re
import unittest
from datetime import timedelta
from urllib.parse import urlparse

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from django.utils import timezone

from cms.api import add_plugin

from danceschool.core.constants import getConstant
from danceschool.core.models import (
    DanceRole, DanceType, DanceTypeLevel, ClassDescription, PricingTier,
    Location, StaffMember, Instructor, Event, Series, EventStaffMember,
    EventOccurrence,
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
