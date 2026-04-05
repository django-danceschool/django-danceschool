import json

from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from ..models import EventOccurrence, Event, PublicEvent, Registration, Invoice
from ..constants import getConstant, REG_VALIDATION_STR
from .defaults import DefaultSchoolTestCase


class RegistrationTest(DefaultSchoolTestCase):

    def test_adding_open_series(self):
        """
        Tests that we can log in as a superuser and add a class series
        from the admin form, and that the series is open for registration.
        """

        # Check that the registration page loads.
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)

        # Check that the Add a class series page loads for the superuser
        self.client.login(username=self.superuser.username, password='pass')
        add_series_response = self.client.get(reverse('admin:core_series_add'))
        self.assertEqual(add_series_response.status_code, 200)
        self.client.logout()

        # Add a class series with occurrences in the future, and check that
        # registration is open.
        s = self.create_series()
        self.assertEqual(s.status, Event.RegStatus.enabled)
        self.assertTrue(s.startTime >= timezone.now() and s.startTime)
        self.assertTrue(s.endTime >= timezone.now() and s.endTime)
        self.assertEqual(s.registrationOpen, True)

    def test_past_series(self):
        '''
        Test that if a class series has its only occurrence in the past, then
        registrationOpen becomes False and the series is no longer available.
        '''

        s = self.create_series()
        self.assertEqual(s.registrationOpen, True)

        # Modify the existing class series to set the only eventoccurrence
        # in the past, and check that registrationOpen is now False.
        ec = s.eventoccurrence_set.first()
        ec.startTime = timezone.now() + timedelta(days=-1)
        ec.endTime = timezone.now() + timedelta(days=-1, hours=1)
        ec.save()
        s.refresh_from_db()

        self.assertEqual(s.registrationOpen, False)
        self.assertEqual(s.status, Event.RegStatus.enabled)

    def test_closed_series(self):
        '''
        Modify an existing class series to set the occurrence back to
        tomorrow, but also create an occurrence far enough in the past
        that registration should be closed, and check that registration
        is in fact closed.
        '''

        s = self.create_series()

        ec = s.eventoccurrence_set.first()
        ec.startTime = timezone.now() + timedelta(days=1)
        ec.endTime = timezone.now() + timedelta(days=1, hours=1)
        ec.save()

        daysBeforeLimit = getConstant('registration__closeAfterDays')

        EventOccurrence.objects.create(
            startTime=timezone.now() + timedelta(days=-1 * daysBeforeLimit - 1),
            endTime=timezone.now() + timedelta(days=-1 * daysBeforeLimit - 1, hours=1),
            event=s,
        )
        s.save()

        self.assertEqual(s.registrationOpen, False)
        self.assertEqual(s.status, Event.RegStatus.enabled)
        # The closed-series section shows series that have already started
        # (startTime <= now) but haven't ended (endTime >= now).  This series
        # has startTime = closeAfterDays+1 days ago and endTime = tomorrow,
        # so it satisfies both conditions.
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Series must appear in the Ongoing Classes section...
        ongoing_idx = content.find('Ongoing Classes')
        self.assertNotEqual(ongoing_idx, -1, 'Ongoing Classes section missing')
        self.assertIn(self.levelOneClassDescription.title, content[ongoing_idx:])
        # ...but must NOT appear in the Upcoming Classes section.
        upcoming_idx = content.find('Upcoming Classes')
        self.assertNotEqual(upcoming_idx, -1, 'Upcoming Classes section missing')
        self.assertNotIn(
            self.levelOneClassDescription.title,
            content[upcoming_idx:ongoing_idx] if upcoming_idx < ongoing_idx
            else content[upcoming_idx:],
        )
        # Closed series must not present any registration quantity inputs.
        self.assertNotContains(response, 'register-quantity')

        # Delete the old occurrence, and check that registration opens back up
        # and the series moves to the Upcoming Classes section.
        s.eventoccurrence_set.filter(startTime__lte=timezone.now()).delete()
        s.save()
        self.assertEqual(s.registrationOpen, True)
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.levelOneClassDescription.title)
        self.assertContains(response, 'register-quantity')

    def test_registration_open_date_blocks_opening(self):
        '''
        When registrationOpenDate is set to a future time and status is
        enabled, registrationOpen must remain False until that date arrives.
        Setting registrationOpenDate to a past time must open registration.
        '''
        future_open = timezone.now() + timedelta(days=2)
        s = self.create_series()

        # Set a future registrationOpenDate and re-save — registration
        # should be blocked even though status is enabled.
        s.registrationOpenDate = future_open
        s.save()
        self.assertEqual(s.registrationOpen, False)

        # The series must not appear on the public registration page (it has a
        # future startTime, so it also won't pass the daysEnd=0 filter on the
        # closed section).
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.levelOneClassDescription.title)

        # Setting registrationOpenDate to a past time should open registration
        # and make the series appear in the Upcoming Classes section.
        s.registrationOpenDate = timezone.now() - timedelta(hours=1)
        s.save()
        self.assertEqual(s.registrationOpen, True)

        response = self.client.get(reverse('registration'))
        self.assertContains(response, self.levelOneClassDescription.title)
        self.assertContains(response, 'register-quantity')

        # Clearing registrationOpenDate entirely should also leave it open.
        s.registrationOpenDate = None
        s.save()
        self.assertEqual(s.registrationOpen, True)

    def test_registration(self):
        '''
        Tests the basic procedures of the registration process using the
        CartView workflow: adding an item to the cart, checking out, filling
        in student information, and verifying the registration summary page.
        '''

        s = self.create_series()

        # The registration page should load and show the open series.
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.levelOneClassDescription.title)
        self.assertContains(response, 'register-quantity')

        # Submit the series to the cart and check out.
        sku = 'EVENT_{}_GENERAL'.format(s.id)
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

        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR].get('invoice_id')
        )
        tr = Registration.objects.filter(invoice=invoice).first()
        self.assertTrue(tr.eventregistration_set.filter(event__id=s.id).exists())
        self.assertFalse(tr.final)
        self.assertEqual(tr.payAtDoor, False)

        # The invoice gross total should match the base price of the series.
        self.assertEqual(invoice.grossTotal, s.getBasePrice())

        # Try to sign up without agreeing to the policies — it should fail.
        post_data = {
            'firstName': 'Test',
            'lastName': 'Customer',
            'email': 'test@customer.com',
        }
        response = self.client.post(reverse('getStudentInfo'), post_data, follow=True)
        self.assertTrue(response.context_data['form'].errors.get('agreeToPolicies'))

        # Now submit a correct form and ensure that it continues to the summary page.
        post_data.update({'agreeToPolicies': True})
        response = self.client.post(reverse('getStudentInfo'), post_data, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])

        # Since there are no discounts or vouchers applied, check that the net price
        # and gross price match.
        self.assertEqual(response.context_data.get('invoice').grossTotal, s.getBasePrice())
        self.assertEqual(response.context_data.get('grossTotal'), response.context_data.get('total'))
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 0)
    

class LinkOnlyViewTest(DefaultSchoolTestCase):
    """
    Diagnostic tests for the UUID-based private link URLs for linkOnly events.
    """

    def _linkonly_series(self):
        s = self.create_series(status=Event.RegStatus.linkOnly)
        # Refresh from DB so we have the canonical uuid value
        s.refresh_from_db()
        return s

    def _linkonly_public_event(self):
        from datetime import timedelta
        start = timezone.now() + timedelta(hours=2)
        pe = PublicEvent(
            title='Link-Only Event',
            slug='link-only-event',
            pricingTier=self.defaultPricing,
            location=self.defaultLocation,
            status=Event.RegStatus.linkOnly,
        )
        pe.save()
        EventOccurrence.objects.create(
            event=pe,
            startTime=start,
            endTime=start + timedelta(hours=1),
        )
        pe.save()
        pe.refresh_from_db()
        return pe

    # --- classViewUUID ---

    def test_linkonly_series_uuid_url_returns_200(self):
        """GET classes/link/<uuid>/ returns 200 for a linkOnly series."""
        s = self._linkonly_series()
        url = reverse('classViewUUID', kwargs={'uuid': s.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_normal_series_uuid_url_returns_200(self):
        """GET classes/link/<uuid>/ also works for an enabled (non-linkOnly) series."""
        s = self.create_series()
        s.refresh_from_db()
        url = reverse('classViewUUID', kwargs={'uuid': s.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_linkonly_series_slug_url_returns_404(self):
        """A linkOnly series must NOT be reachable via the normal slug URL."""
        s = self._linkonly_series()
        from calendar import month_name as mn
        url = reverse('classView', kwargs={
            'year': s.year,
            'month': list(mn)[s.month],
            'slug': s.classDescription.slug,
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_uuid_url_sets_link_authorized_in_session(self):
        """Visiting classes/link/<uuid>/ adds the event pk to session link_authorized."""
        s = self._linkonly_series()
        url = reverse('classViewUUID', kwargs={'uuid': s.uuid})
        self.client.get(url)
        link_authorized = self.client.session.get(REG_VALIDATION_STR, {}).get('link_authorized', [])
        self.assertIn(s.pk, link_authorized)

    def test_uuid_url_passes_link_authorized_context(self):
        """Visiting classes/link/<uuid>/ sets link_authorized=True in template context."""
        s = self._linkonly_series()
        url = reverse('classViewUUID', kwargs={'uuid': s.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context.get('link_authorized'))

    # --- eventViewUUID ---

    def test_linkonly_event_uuid_url_returns_200(self):
        """GET events/link/<uuid>/ returns 200 for a linkOnly public event."""
        pe = self._linkonly_public_event()
        url = reverse('eventViewUUID', kwargs={'uuid': pe.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_linkonly_event_slug_url_returns_404(self):
        """A linkOnly public event must NOT be reachable via the normal slug URL."""
        pe = self._linkonly_public_event()
        from calendar import month_name as mn
        url = reverse('eventView', kwargs={
            'year': pe.year,
            'month': list(mn)[pe.month],
            'slug': pe.slug,
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
