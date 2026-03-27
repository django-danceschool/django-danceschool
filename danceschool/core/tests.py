"""
This file contains basic tests for the core app.
"""

import json

from django.urls import reverse
from django.utils import timezone
from django.test import TestCase
from django.contrib.auth.models import User

from datetime import timedelta
from calendar import month_name
import dateutil.parser
from itertools import chain

from dynamic_preferences.registries import global_preferences_registry

from .models import EventOccurrence, Event, Series, PublicEvent, Registration, Invoice, InvoiceItem, EventRole, EventStaffMember
from .constants import getConstant, updateConstant, REG_VALIDATION_STR
from .utils.tests import DefaultSchoolTestCase


class RegistrationTest(DefaultSchoolTestCase):

    def test_adding_open_series(self):
        """
        Tests that we can log in as a superuser and add a class series
        from the admin form, and that that class shows up on the
        registration page.
        """

        # First, check that the registration page loads, and that there
        # are no open or closed series on the registration page.
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context_data['regOpenSeries'], [])
        self.assertQuerySetEqual(response.context_data['regClosedSeries'], [])

        # Check that the Add a class series page loads for the superuser
        self.client.login(username=self.superuser.username, password='pass')
        add_series_response = self.client.get(reverse('admin:core_series_add'))
        self.assertEqual(add_series_response.status_code, 200)
        self.client.logout()

        # Add a class series with occurrences in the future, and check that
        # registration is open by looking at the registration page
        s = self.create_series()
        self.assertEqual(s.status, Event.RegStatus.enabled)
        self.assertTrue(s.startTime >= timezone.now() and s.startTime)
        self.assertTrue(s.endTime >= timezone.now() and s.endTime)
        self.assertEqual(s.registrationOpen, True)
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context_data['regOpenSeries'], [s, ])
        self.assertQuerySetEqual(response.context_data['regClosedSeries'], [])

    def test_past_series(self):
        '''
        Test that if a class series has its only occurrence in the past, then
        the series no longer shows up on the registration page at all.
        '''

        s = self.create_series()
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context_data['regOpenSeries'], [s, ])
        self.assertQuerySetEqual(response.context_data['regClosedSeries'], [])

        # Modify the existing class series to set the only eventoccurrence
        # in the past, and check that it now longer shows up at all
        ec = s.eventoccurrence_set.first()
        ec.startTime = timezone.now() + timedelta(days=-1)
        ec.endTime = timezone.now() + timedelta(days=-1, hours=1)
        ec.save()
        s.refresh_from_db()

        self.assertEqual(s.registrationOpen, False)
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context_data['regOpenSeries'], [])
        self.assertQuerySetEqual(response.context_data['regClosedSeries'], [])
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
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context_data['regOpenSeries'], [])
        self.assertQuerySetEqual(response.context_data['regClosedSeries'], [s, ])
        self.assertEqual(s.status, Event.RegStatus.enabled)

        # Delete the old occurrence, and check that registration opens back up
        s.eventoccurrence_set.filter(startTime__lte=timezone.now()).delete()
        s.save()
        self.assertEqual(s.registrationOpen, True)
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context_data['regOpenSeries'], [s, ])
        self.assertQuerySetEqual(response.context_data['regClosedSeries'], [])

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

        # The series must not appear on the public registration page.
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context_data['regOpenSeries'], [])

        # Setting registrationOpenDate to a past time should open registration.
        s.registrationOpenDate = timezone.now() - timedelta(hours=1)
        s.save()
        self.assertEqual(s.registrationOpen, True)

        response = self.client.get(reverse('registration'))
        self.assertQuerySetEqual(response.context_data['regOpenSeries'], [s, ])

        # Clearing registrationOpenDate entirely should also leave it open.
        s.registrationOpenDate = None
        s.save()
        self.assertEqual(s.registrationOpen, True)

    def test_individual_class_page_visibility(self):
        '''
        Check that the individual class page for a series is working,
        and that visibility restrictions are applied depending on the status of
        the series
        '''

        s = self.create_series()

        # Check that the individual class page for this series is working
        response = self.client.get(reverse(
            'classView', args=(s.year, month_name[s.month], s.slug)
        ))
        self.assertEqual(response.status_code, 200)

        # Change the registration status to link-only, and check that the individual
        # event registration page works even though the Event does not show up publicly
        s.status = Event.RegStatus.linkOnly
        s.save()

        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context_data['regOpenSeries'], [])
        self.assertQuerySetEqual(response.context_data['regClosedSeries'], [])

        response = self.client.get(reverse('singleClassRegistration', args=(str(s.uuid),)))
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context_data['regOpenSeries'], [s, ])

        response = self.client.get(reverse('classView', args=(s.year, month_name[s.month], s.slug)))
        self.assertEqual(response.status_code, 404)

        # Change the event status to hidden, and check that the event does not show up
        # anywhere.
        s.status = Event.RegStatus.hidden
        s.save()

        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context_data['regOpenSeries'], [])
        self.assertQuerySetEqual(response.context_data['regClosedSeries'], [])

        response = self.client.get(reverse('singleClassRegistration', args=(str(s.uuid),)))
        self.assertEqual(response.status_code, 404)

        response = self.client.get(reverse('classView', args=(s.year, month_name[s.month], s.slug)))
        self.assertEqual(response.status_code, 404)

    def test_registration(self):
        '''
        This tests the basic procedures of the registration process, as well as
        the restrictions of registering for only one role, registering for something,
        and requiring agreement to school policies
        '''

        s = self.create_series()

        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context_data['regOpenSeries'], [s, ])

        # Since this is an anonymous user, check that there is no option to register
        # at-the-door
        self.assertFalse(response.context_data['form'].fields.get('payAtDoor'))

        # Attempt to submit an empty form and ensure that it fails
        post_data = {}
        response = self.client.post(reverse('registration'), post_data, follow=True)
        self.assertTrue(response.context_data['form'].errors.get('__all__'))

        # Sign up for the series, and check that we proceed to the student information page.
        # Because of the way that roles are encoded on this form, we just grab the value to pass
        # from the form itself.
        post_data = {'series_%s_%s' % (
            s.id, response.context_data['form'].fields['series_%s' % s.id].field_choices[0].get('value')
        ): [1,]}

        response = self.client.post(reverse('registration'), post_data, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse('getStudentInfo'), 302)])

        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR].get('invoice_id')
        )
        tr = Registration.objects.filter(invoice=invoice).first()
        self.assertTrue(tr.eventregistration_set.filter(event__id=s.id).exists())
        self.assertFalse(tr.final)
        self.assertEqual(tr.payAtDoor, False)

        # Check that the student info page lists the correct item amounts and subtotal
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(response.context_data.get('invoice').total, s.getBasePrice())

        # Try to sign up without agreeing to the policies, and ensure that it fails
        post_data = {
            'firstName': 'Test',
            'lastName': 'Customer',
            'email': 'test@customer.com',
        }

        response = self.client.post(reverse('getStudentInfo'), post_data, follow=True)
        self.assertTrue(response.context_data['form'].errors.get('agreeToPolicies'))

        # Now submit a correct form and ensure that it continues to the summary page
        post_data.update({'agreeToPolicies': True})
        response = self.client.post(reverse('getStudentInfo'), post_data, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])

        # Since there are no discounts or vouchers applied, check that the net price
        # and gross price match
        self.assertEqual(response.context_data.get('invoice').grossTotal, s.getBasePrice())
        self.assertEqual(response.context_data.get('grossTotal'), response.context_data.get('total'))
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 0)


class CalendarTest(DefaultSchoolTestCase):

    def test_calendar_page(self):
        """
        Add a calendar page using the same method as the setupschool
        script.  Check that the calendar page loads, then add a Series
        and make sure that it shows up on the calendar at the correct time.
        """
        s = self.create_series()

        # Check that the series shows up in the JSON calendar feed, used by
        # the calendar page
        response = self.client.get(reverse('jsonCalendarFeed'))
        self.assertEqual(response.status_code, 200)

        # Check that all occurrences show up in the calendar feed
        occurrence_ids = [
            'event_%s_%s' % (s.id, x.id) for x in s.eventoccurrence_set.filter(cancelled=False)
        ]
        calendar_items = [x for x in response.json() if x['id_number'] == s.id]
        self.assertEqual(len(occurrence_ids), len(calendar_items))

        # Check that the time shown matches what's in the database
        # (no issues with time zones). We check that it's within one second
        # because the feed may be less precise than microseconds.
        this_occurrence = s.eventoccurrence_set.first()
        this_calendar_item = [
            x for x in calendar_items if
            x['id'] == 'event_%s_%s' % (s.id, this_occurrence.id)
        ]
        self.assertTrue(
            dateutil.parser.parse(this_calendar_item[0]['start']) -
            this_occurrence.startTime <= timedelta(seconds=1)
        )


class SubstituteTeacherTest(DefaultSchoolTestCase):

    def test_subform_access(self):
        '''
        Test that the substitute teaching form can be accessed by
        a superuser but not an anonymous user, and that a new instructor
        can report substitute teaching for a new series
        '''

        s = self.create_series()
        i = self.create_instructor()

        # This shouldn't work until logged
        response = self.client.get(reverse('substituteTeacherForm'))
        self.assertEqual(response.status_code, 302)
        self.client.login(username=self.superuser.username, password='pass')
        response = self.client.get(reverse('substituteTeacherForm'))
        self.assertEqual(response.status_code, 200)

        # Check that substitute teaching is an available category
        self.assertIn(
            (getConstant('general__eventStaffCategorySubstitute').id, 'Substitute Teaching'),
            response.context_data.get('form').fields.get('category').choices
        )

        # Check that the series shows up as available for substituting and
        # that the new instructor is able to substitute
        self.assertIn(
            (s.id, s.__str__()),
            response.context_data.get('form').fields.get('event').choices
        )
        self.assertIn(
            (i.id, i.fullName),
            response.context_data.get('form').fields.get('staffMember').choices
        )

    def test_subform_submission(self):
        '''
        Report substitute teaching of a new instructor for a new series,
        and ensure that the submission only succeeds once, and only if
        the person is not subbing for themselves
        '''

        s = self.create_series()
        i = self.create_instructor()
        # create_series adds defaultInstructor as an EventStaffMember (Instructor
        # category).  updateSeriesAttributes returns EventStaffMember PKs, not
        # StaffMember PKs, so look that up here for use throughout the test.
        esm = EventStaffMember.objects.get(
            event=s,
            staffMember=self.defaultInstructor,
            category=getConstant('general__eventStaffCategoryInstructor'),
        )

        # Login and access the form
        self.client.login(username=self.superuser.username, password='pass')
        response = self.client.get(reverse('substituteTeacherForm'))
        self.assertEqual(response.status_code, 200)

        ajax_response = self.client.post(
            reverse('ajaxhandler_submitsubstitutefilter'),
            {
                'event': s.id, 'occurrences[]': s.eventoccurrence_set.values_list('id', flat=True),
                'category': getConstant('general__eventStaffCategorySubstitute').id,
            }
        )
        self.assertEqual(ajax_response.status_code, 200)
        self.assertIn(
            str(esm.id),
            ajax_response.json()['id_replacedStaffMember'].keys()
        )
        self.assertIn(
            str(s.eventoccurrence_set.first().id),
            ajax_response.json()['id_occurrences'].keys()
        )

        # Try to report the defaultInstructor as a sub for themselves and
        # check that it fails
        post_data = {
            'category': getConstant('general__eventStaffCategorySubstitute').id,
            'event': s.id,
            'staffMember': self.defaultInstructor.id,
            'replacedStaffMember': esm.id,
            'occurrences': [s.eventoccurrence_set.first().id, ],
            'submissionUser': self.superuser.id,
        }
        response = self.client.post(reverse('substituteTeacherForm'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'Staffers cannot substitute for themselves.',
            response.context_data['form'].errors.get('replacedStaffMember')
        )

        # Post with no replacedStaffMember and not staffMember and ensure it fails
        post_data.pop('replacedStaffMember')
        post_data.pop('staffMember')
        response = self.client.post(reverse('substituteTeacherForm'), post_data)
        self.assertIn('This field is required.', response.context_data['form'].errors.get('staffMember'))
        self.assertIn(
            'This field is required.', response.context_data['form'].errors.get('replacedStaffMember')
        )

        # Now update and ensure that it worked
        post_data.update({'staffMember': i.id, 'replacedStaffMember': esm.id})
        response = self.client.post(reverse('substituteTeacherForm'), post_data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            s.eventstaffmember_set.filter(
                category=getConstant('general__eventStaffCategorySubstitute'), staffMember=i
            ).exists()
        )

        # Try submitting the same thing again and ensure that it fails
        response = self.client.post(reverse('substituteTeacherForm'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'Select a valid choice. That choice is not one of the available choices.',
            response.context_data['form'].errors.get('replacedStaffMember')
        )


class AdminTest(TestCase):
    '''
    Check that all admin add and changelist pages are functional at least for
    superusers.
    '''

    REDIRECT_ADMIN_OBJECTS = ['AliasContentVersion', 'PageContentVersion']

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            'admin',
            'admin@test.com',
            'pass',
            first_name='Frankie',
            last_name='Manning',
        )

    def test_admin_pages(self):
        '''
        Log in as superuser, get the list of admin pages, and check that all
        changelist and add pages return 200.
        '''
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        
        self.client.login(username=self.superuser.username, password='pass')
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)

        app_list = response.context_data.get('app_list', [])
        self.assertNotEqual(app_list, [])

        for model in chain(*[x.get('models', []) for x in app_list]):
            if model.get('admin_url') and (
                model.get('object_name') not in self.REDIRECT_ADMIN_OBJECTS
            ):
                response = self.client.get(model['admin_url'])
                self.assertEqual(response.status_code, 200)
            if model.get('add_url'):
                response = self.client.get(model['add_url'])
                self.assertEqual(response.status_code, 200)


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


class SalesTaxDifferentiationTest(DefaultSchoolTestCase):
    '''
    Verifies that SeriesSalesTaxRate and PublicEventSalesTaxRate are applied
    independently to class series and public event registrations, respectively,
    through both the CartView and ClassRegistrationView (AjaxClassRegistrationView)
    checkout workflows.
    '''

    SERIES_TAX_RATE = 10.0
    EVENT_TAX_RATE = 5.0

    def setUp(self):
        self.gp = global_preferences_registry.manager()
        self.gp['registration__seriesSalesTaxRate'] = self.SERIES_TAX_RATE
        self.gp['registration__publicEventSalesTaxRate'] = self.EVENT_TAX_RATE

        self.series = self.create_series()

        start = timezone.now() + timedelta(days=1)
        self.public_event = PublicEvent(
            title='Test Tax Event',
            slug='test-tax-event',
            pricingTier=self.defaultPricing,
            location=self.defaultLocation,
            status=Event.RegStatus.enabled,
        )
        self.public_event.save()
        EventOccurrence.objects.create(
            event=self.public_event,
            startTime=start,
            endTime=start + timedelta(hours=1),
        )
        self.public_event.save()

    def tearDown(self):
        self.gp['registration__seriesSalesTaxRate'] = 0.0
        self.gp['registration__publicEventSalesTaxRate'] = 0.0

    # --- CartView workflow ---

    def _cart_checkout(self, event):
        sku = f'EVENT_{event.id}_GENERAL'
        return self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{'item_type': 'Event', 'item_id': event.id,
                           'sku': sku, 'quantity': 1}],
                'checkout': True,
            }),
            content_type='application/json',
        )

    def _get_invoice_items(self):
        invoice_id = self.client.session[REG_VALIDATION_STR].get('invoice_id')
        invoice = Invoice.objects.get(id=invoice_id)
        return list(invoice.invoiceitem_set.all())

    def test_cart_series_uses_series_tax_rate(self):
        '''CartView checkout for a Series applies seriesSalesTaxRate.'''
        self._cart_checkout(self.series)
        items = self._get_invoice_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].taxRate, self.SERIES_TAX_RATE)

    def test_cart_public_event_uses_public_event_tax_rate(self):
        '''CartView checkout for a PublicEvent applies publicEventSalesTaxRate.'''
        self._cart_checkout(self.public_event)
        items = self._get_invoice_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].taxRate, self.EVENT_TAX_RATE)

    def test_cart_series_and_public_event_get_different_rates(self):
        '''
        When both a Series and a PublicEvent are in the cart, their invoice
        items carry different tax rates matching each type's preference.
        '''
        series_sku = f'EVENT_{self.series.id}_GENERAL'
        event_sku = f'EVENT_{self.public_event.id}_GENERAL'
        self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [
                    {'item_type': 'Event', 'item_id': self.series.id,
                     'sku': series_sku, 'quantity': 1},
                    {'item_type': 'Event', 'item_id': self.public_event.id,
                     'sku': event_sku, 'quantity': 1},
                ],
                'checkout': True,
            }),
            content_type='application/json',
        )
        invoice_id = self.client.session[REG_VALIDATION_STR].get('invoice_id')
        invoice = Invoice.objects.get(id=invoice_id)

        series_regs = invoice.registration.eventregistration_set.filter(event=self.series)
        event_regs = invoice.registration.eventregistration_set.filter(event=self.public_event)
        self.assertTrue(series_regs.exists())
        self.assertTrue(event_regs.exists())

        series_item = series_regs.first().invoiceItem
        event_item = event_regs.first().invoiceItem
        self.assertEqual(series_item.taxRate, self.SERIES_TAX_RATE)
        self.assertEqual(event_item.taxRate, self.EVENT_TAX_RATE)

    # --- ClassRegistrationView (AjaxClassRegistrationView) workflow ---

    def _classreg_checkout(self, event):
        '''Submit the ClassChoiceForm for the given event and return the response.'''
        response = self.client.get(reverse('registration'))
        field_name = f'{event.fieldPrefix}_{event.id}'
        field = response.context_data['form'].fields[field_name]
        choice_value = field.field_choices[0].get('value')
        post_data = {f'{field_name}_{choice_value}': [1]}
        return self.client.post(reverse('registration'), post_data, follow=True)

    def test_classreg_series_uses_series_tax_rate(self):
        '''ClassRegistrationView checkout for a Series applies seriesSalesTaxRate.'''
        response = self._classreg_checkout(self.series)
        self.assertEqual(response.redirect_chain, [(reverse('getStudentInfo'), 302)])
        items = self._get_invoice_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].taxRate, self.SERIES_TAX_RATE)

    def test_classreg_public_event_uses_public_event_tax_rate(self):
        '''ClassRegistrationView checkout for a PublicEvent applies publicEventSalesTaxRate.'''
        response = self._classreg_checkout(self.public_event)
        self.assertEqual(response.redirect_chain, [(reverse('getStudentInfo'), 302)])
        items = self._get_invoice_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].taxRate, self.EVENT_TAX_RATE)


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
