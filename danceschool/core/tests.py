"""
This file contains basic tests for the core app.
"""

from django.core.urlresolvers import reverse
from django.utils import timezone

from datetime import timedelta
from calendar import month_name
import dateutil.parser

from .models import EventOccurrence, Event, TemporaryRegistration
from .constants import getConstant, REG_VALIDATION_STR
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
        self.assertEqual(response.status_code,200)
        self.assertQuerysetEqual(response.context['regOpenSeries'], [])
        self.assertQuerysetEqual(response.context['regClosedSeries'], [])

        # Check that the Add a class series page loads for the superuser
        self.client.login(username=self.superuser.username,password='pass')
        add_series_response = self.client.get(reverse('admin:core_series_add'))
        self.assertEqual(add_series_response.status_code,200)
        self.client.logout()

        # Add a class series with occurrences in the future, and check that
        # registration is open by looking at the registration page
        s = self.create_series()
        self.assertEqual(s.status,Event.RegStatus.enabled)
        self.assertTrue(s.startTime >= timezone.now() and s.startTime)
        self.assertTrue(s.endTime >= timezone.now() and s.endTime)
        self.assertEqual(s.registrationOpen,True)
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code,200)
        self.assertQuerysetEqual(response.context['regOpenSeries'], [s.__repr__(),])
        self.assertQuerysetEqual(response.context['regClosedSeries'], [])

    def test_past_series(self):
        '''
        Test that if a class series has its only occurrence in the past, then
        the series no longer shows up on the registration page at all.
        '''

        s = self.create_series()
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code,200)
        self.assertQuerysetEqual(response.context['regOpenSeries'], [s.__repr__(),])
        self.assertQuerysetEqual(response.context['regClosedSeries'], [])

        # Modify the existing class series to set the only eventoccurrence
        # in the past, and check that it now longer shows up at all
        ec = s.eventoccurrence_set.first()
        ec.startTime = timezone.now() + timedelta(days=-1)
        ec.endTime = timezone.now() + timedelta(days=-1,hours=1)
        ec.save()
        s.save()

        self.assertEqual(s.registrationOpen,False)
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code,200)
        self.assertQuerysetEqual(response.context['regOpenSeries'], [])
        self.assertQuerysetEqual(response.context['regClosedSeries'], [])
        self.assertEqual(s.status,Event.RegStatus.enabled)

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
        ec.endTime = timezone.now() + timedelta(days=1,hours=1)
        ec.save()

        daysBeforeLimit = getConstant('registration__closeAfterDays')

        EventOccurrence.objects.create(
            startTime=timezone.now() + timedelta(days=-1 * daysBeforeLimit - 1),
            endTime=timezone.now() + timedelta(days=-1 * daysBeforeLimit - 1, hours=1),
            event=s,
        )
        s.save()

        self.assertEqual(s.registrationOpen,False)
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code,200)
        self.assertQuerysetEqual(response.context['regOpenSeries'], [])
        self.assertQuerysetEqual(response.context['regClosedSeries'], [s.__repr__(),])
        self.assertEqual(s.status,Event.RegStatus.enabled)

        # Delete the old occurrence, and check that registration opens back up
        s.eventoccurrence_set.filter(startTime__lte=timezone.now()).delete()
        s.save()
        self.assertEqual(s.registrationOpen,True)
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code,200)
        self.assertQuerysetEqual(response.context['regOpenSeries'], [s.__repr__(),])
        self.assertQuerysetEqual(response.context['regClosedSeries'], [])

    def test_individual_class_page_visibility(self):
        '''
        Check that the individual class page for a series is working,
        and that visibility restrictions are applied depending on the status of
        the series
        '''

        s = self.create_series()

        # Check that the individual class page for this series is working
        response = self.client.get(reverse('classView',args=(s.year,month_name[s.month],s.slug)))
        self.assertEqual(response.status_code,200)

        # Change the registration status to link-only, and check that the individual
        # event registration page works even though the Event does not show up publicly
        s.status = Event.RegStatus.linkOnly
        s.save()

        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code,200)
        self.assertQuerysetEqual(response.context['regOpenSeries'], [])
        self.assertQuerysetEqual(response.context['regClosedSeries'], [])

        response = self.client.get(reverse('singleClassRegistration', args=(str(s.uuid),)))
        self.assertEqual(response.status_code,200)
        self.assertQuerysetEqual(response.context['regOpenSeries'], [s.__repr__(),])

        response = self.client.get(reverse('classView',args=(s.year,month_name[s.month],s.slug)))
        self.assertEqual(response.status_code,404)

        # Change the event status to hidden, and check that the event does not show up
        # anywhere.
        s.status = Event.RegStatus.hidden
        s.save()

        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code,200)
        self.assertQuerysetEqual(response.context['regOpenSeries'], [])
        self.assertQuerysetEqual(response.context['regClosedSeries'], [])

        response = self.client.get(reverse('singleClassRegistration', args=(str(s.uuid),)))
        self.assertEqual(response.status_code,404)

        response = self.client.get(reverse('classView',args=(s.year,month_name[s.month],s.slug)))
        self.assertEqual(response.status_code,404)

    def test_registration(self):
        '''
        This tests the basic procedures of the registration process, as well as
        the restrictions of registering for only one role, registering for something,
        and requiring agreement to school policies
        '''

        s = self.create_series()

        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code,200)
        self.assertQuerysetEqual(response.context['regOpenSeries'], [s.__repr__(),])

        # Since this is an anonymous user, check that there is no option to register
        # at-the-door
        self.assertFalse(response.context_data['form'].fields.get('payAtDoor'))

        # Attempt to submit an empty form and ensure that it fails
        post_data = {}
        response = self.client.post(reverse('registration'),post_data,follow=True)
        self.assertTrue(response.context_data['form'].errors.get('__all__'))

        # Attempt to sign up for multiple roles for the same series and ensure that it fails
        post_data = {
            'event_%s' % s.id: (
                response.context_data['form'].fields['event_%s' % s.id].choices[0][0],
                response.context_data['form'].fields['event_%s' % s.id].choices[1][0]
            )
        }
        response = self.client.post(reverse('registration'),post_data,follow=True)
        self.assertEqual(response.context_data['form'].errors.get('__all__'), ['Must select only one role.',])

        # Sign up for the series, and check that we proceed to the student information page.
        # Because of the way that roles are encoded on this form, we just grab the value to pass
        # from the form itself.
        post_data = {'event_%s' % s.id: response.context_data['form'].fields['event_%s' % s.id].choices[0][0]}

        response = self.client.post(reverse('registration'),post_data,follow=True)
        self.assertEqual(response.redirect_chain,[(reverse('getStudentInfo'), 302)])

        tr = TemporaryRegistration.objects.get(id=self.client.session[REG_VALIDATION_STR].get('temporaryRegistrationId'))
        self.assertTrue(tr.temporaryeventregistration_set.filter(event__id=s.id).exists())
        self.assertEqual(tr.payAtDoor, False)

        # Check that the student info page lists the correct item amounts and subtotal
        self.assertEqual(tr.temporaryeventregistration_set.get(event__id=s.id).price, s.getBasePrice())
        self.assertEqual(response.context_data.get('subtotal'), s.getBasePrice())

        # Try to sign up without agreeing to the policies, and ensure that it fails
        post_data = {
            'firstName': 'Test',
            'lastName': 'Customer',
            'email': 'test@customer.com',
        }

        response = self.client.post(reverse('getStudentInfo'),post_data,follow=True)
        self.assertTrue(response.context_data['form'].errors.get('agreeToPolicies'))

        # Now submit a correct form and ensure that it continues to the summary page
        post_data.update({'agreeToPolicies': True})
        response = self.client.post(reverse('getStudentInfo'),post_data,follow=True)
        self.assertEqual(response.redirect_chain,[(reverse('showRegSummary'), 302)])

        # Since there are no discounts or vouchers applied, check that the net price
        # and gross price match
        self.assertEqual(response.context_data.get('totalPrice'), s.getBasePrice())
        self.assertEqual(response.context_data.get('netPrice'),response.context_data.get('totalPrice'))
        self.assertEqual(response.context_data.get('is_free'),False)
        self.assertEqual(response.context_data.get('total_discount_amount'),0)


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
        self.assertEqual(response.status_code,200)

        # Check that all occurrences show up in the calendar feed
        occurrence_ids = ['event_%s_%s' % (s.id,x.id) for x in s.eventoccurrence_set.filter(cancelled=False)]
        calendar_items = [x for x in response.json() if x['id_number'] == s.id]
        self.assertEqual(len(occurrence_ids), len(calendar_items))

        # Check that the time shown matches what's in the database (no issues with time zones)
        # We check that it's within one second because the feed may be less precise than microseconds.
        this_occurrence = s.eventoccurrence_set.first()
        this_calendar_item = [x for x in calendar_items if x['id'] == 'event_%s_%s' % (s.id, this_occurrence.id)]
        self.assertTrue(dateutil.parser.parse(this_calendar_item[0]['start']) - this_occurrence.startTime <= timedelta(seconds=1))


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
        self.assertEqual(response.status_code,302)
        self.client.login(username=self.superuser.username,password='pass')
        response = self.client.get(reverse('substituteTeacherForm'))
        self.assertEqual(response.status_code,200)

        # Check that substitute teaching is an available category
        self.assertIn((getConstant('general__eventStaffCategorySubstitute').id,'Substitute Teaching'),response.context_data.get('form').fields.get('category').choices)

        # Check that the series shows up as available for substituting and
        # that the new instructor is able to substitute
        self.assertIn((s.id, s.__str__()),response.context_data.get('form').fields.get('event').choices)
        self.assertIn((i.id, i.fullName),response.context_data.get('form').fields.get('staffMember').choices)

    def test_subform_submission(self):
        '''
        Report substitute teaching of a new instructor for a new series,
        and ensure that the submission only succeeds once, and only if
        the person is not subbing for themselves
        '''

        s = self.create_series()
        i = self.create_instructor()

        # Login and access the form
        self.client.login(username=self.superuser.username,password='pass')
        response = self.client.get(reverse('substituteTeacherForm'))
        self.assertEqual(response.status_code,200)

        ajax_response = self.client.post(reverse('ajaxhandler_submitsubstitutefilter'),{'event': s.id})
        self.assertEqual(ajax_response.status_code,200)
        self.assertIn(str(self.defaultInstructor.id), ajax_response.json()['id_replacedStaffMember'].keys())
        self.assertIn(str(s.eventoccurrence_set.first().id), ajax_response.json()['id_occurrences'].keys())

        # Try to report the defaultInstructor as a sub for themselves and
        # check that it fails
        post_data = {
            'category': getConstant('general__eventStaffCategorySubstitute').id,
            'event': s.id,
            'staffMember': self.defaultInstructor.id,
            'replacedStaffMember': self.defaultInstructor.id,
            'occurrences': [s.eventoccurrence_set.first().id,],
            'submissionUser': self.superuser.id,
        }
        response = self.client.post(reverse('substituteTeacherForm'),post_data)
        self.assertEqual(response.status_code,200)
        self.assertIn('You cannot substitute teach for a class in which you were an instructor.',response.context_data['form'].errors.get('event'))

        # Post with no replacedStaffMember and not staffMember and ensure it fails
        post_data.pop('replacedStaffMember')
        post_data.pop('staffMember')
        response = self.client.post(reverse('substituteTeacherForm'),post_data)
        self.assertIn('This field is required.',response.context_data['form'].errors.get('staffMember'))
        self.assertIn('This field is required.',response.context_data['form'].errors.get('replacedStaffMember'))

        # Now update and ensure that it worked
        post_data.update({'staffMember': i.id, 'replacedStaffMember': self.defaultInstructor.id})
        response = self.client.post(reverse('substituteTeacherForm'),post_data)
        self.assertEqual(response.status_code,302)
        self.assertTrue(s.eventstaffmember_set.filter(category=getConstant('general__eventStaffCategorySubstitute'),staffMember=i).exists())

        # Try submitting the same thing again and ensure that it fails
        response = self.client.post(reverse('substituteTeacherForm'),post_data)
        self.assertEqual(response.status_code,200)
        self.assertIn('One or more classes you have selected already has a substitute teacher for that class.',response.context_data['form'].errors.get('occurrences'))
