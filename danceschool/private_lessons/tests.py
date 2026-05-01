from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from datetime import timedelta
from dynamic_preferences.registries import global_preferences_registry

from danceschool.core.models import (
    Invoice, Instructor, EmailTemplate, Event, EventStaffMember,
)
from danceschool.core.constants import REG_VALIDATION_STR, getConstant
from danceschool.core.tests.defaults import DefaultSchoolTestCase

from .constants import PRIVATELESSON_VALIDATION_STR
from .models import InstructorAvailabilitySlot, PrivateLessonEvent, InstructorPrivateLessonDetails


class PrivateLessonTestCase(DefaultSchoolTestCase):
    '''
    Base test case that extends DefaultSchoolTestCase with private-lesson-specific
    setup: marks the default instructor as available for private lessons, creates
    InstructorPrivateLessonDetails (with roles and a default pricing tier), and
    resets all relevant dynamic preferences before each test.
    '''

    LESSON_TAX_RATE = 8.0

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        # Mark the default instructor as available for private lessons.
        Instructor.objects.filter(staffMember=cls.defaultInstructor).update(availableForPrivates=True)

        cls.pl_details = InstructorPrivateLessonDetails.objects.create(
            instructor=cls.defaultInstructor,
            defaultPricingTier=cls.defaultPricing,
        )
        cls.pl_details.roles.set(cls.defaultDanceRoles)

    def setUp(self):
        self.gp = global_preferences_registry.manager()

        # Lesson-length choices: 30, 60, 90 minutes.
        self.gp['privateLessons__minimumLessonLength'] = 30
        self.gp['privateLessons__maximumLessonLength'] = 90
        self.gp['privateLessons__lessonLengthInterval'] = 30
        self.gp['privateLessons__defaultLessonLength'] = 60

        # Booking window: open now through 30 days from now.
        self.gp['privateLessons__openBookingDays'] = 30
        self.gp['privateLessons__closeBookingDays'] = 0

        # Feature flags
        self.gp['privateLessons__allowRegistration'] = True
        self.gp['privateLessons__allowPublicBooking'] = True
        self.gp['privateLessons__notifyInstructor'] = True
        self.gp['privateLessons__salesTaxRate'] = self.LESSON_TAX_RATE

        # Create a single 30-minute available slot starting tomorrow.
        self.slot = InstructorAvailabilitySlot.objects.create(
            instructor=self.defaultInstructor.instructor,
            pricingTier=self.defaultPricing,
            location=self.defaultLocation,
            startTime=timezone.now() + timedelta(days=1),
            duration=30,
            status=InstructorAvailabilitySlot.SlotStatus.available,
        )
        self.role = self.defaultDanceRoles.first()

    def _book_slot(self, slot=None, duration=30, extra=None):
        '''POST to bookPrivateLesson. Returns the response.'''
        slot = slot or self.slot
        data = {
            'slotId': slot.id,
            'duration': duration,
            'role': self.role.id,
            'participants': 1,
            'comments': '',
        }
        if extra:
            data.update(extra)
        return self.client.post(reverse('bookPrivateLesson'), data=data)


# ---------------------------------------------------------------------------
# Availability feed
# ---------------------------------------------------------------------------

class AvailabilityFeedTest(PrivateLessonTestCase):
    '''Tests that the JSON availability feed reflects the slots in the database.'''

    def test_available_slot_appears_in_feed(self):
        '''An available slot within the booking window is returned by the feed.'''
        self.client.force_login(self.nonStaffUser)
        url = reverse(
            'jsonPrivateLessonAvailabilityFeed',
            kwargs={'instructor_id': self.defaultInstructor.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        events = response.json()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['id_number'], self.slot.id)
        self.assertEqual(events[0]['status'], InstructorAvailabilitySlot.SlotStatus.available)

    def test_unavailable_slot_hidden_from_non_staff_feed(self):
        '''Slots marked unavailable are filtered out for users without edit permission.'''
        self.slot.status = InstructorAvailabilitySlot.SlotStatus.unavailable
        self.slot.save()
        self.client.force_login(self.nonStaffUser)
        url = reverse(
            'jsonPrivateLessonAvailabilityFeed',
            kwargs={'instructor_id': self.defaultInstructor.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.json(), [])

    def test_slot_outside_booking_window_hidden_from_feed(self):
        '''A slot outside the openBookingDays window is not visible.'''
        self.gp['privateLessons__openBookingDays'] = 0  # effectively close all booking
        self.client.force_login(self.nonStaffUser)
        url = reverse(
            'jsonPrivateLessonAvailabilityFeed',
            kwargs={'instructor_id': self.defaultInstructor.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.json(), [])


# ---------------------------------------------------------------------------
# Booking → registration path (allowRegistration=True, slot has pricing tier)
# ---------------------------------------------------------------------------

class BookingWithRegistrationTest(PrivateLessonTestCase):
    '''
    Tests the booking path where allowRegistration=True and the slot has a
    pricing tier, so the user is directed to the standard registration flow.
    '''

    def test_booking_redirects_to_student_info(self):
        '''A successful booking redirects to getStudentInfo.'''
        self.client.force_login(self.nonStaffUser)
        response = self._book_slot()
        self.assertRedirects(
            response, reverse('getStudentInfo'), fetch_redirect_response=False
        )

    def test_booking_creates_invoice_with_private_lesson_tax_rate(self):
        '''The invoice item created during booking carries privateLessons__salesTaxRate.'''
        self.client.force_login(self.nonStaffUser)
        self._book_slot()

        invoice_id = self.client.session[REG_VALIDATION_STR]['invoice_id']
        invoice = Invoice.objects.get(id=invoice_id)
        items = list(invoice.invoiceitem_set.all())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].taxRate, self.LESSON_TAX_RATE)

    def test_booking_applies_buyer_pays_tax_correctly(self):
        '''
        When buyerPaysSalesTax=True, taxes are added on top of the item total
        rather than extracted from it.
        '''
        self.gp['registration__buyerPaysSalesTax'] = True
        self.client.force_login(self.nonStaffUser)
        self._book_slot()

        invoice_id = self.client.session[REG_VALIDATION_STR]['invoice_id']
        invoice = Invoice.objects.get(id=invoice_id)
        item = invoice.invoiceitem_set.first()

        expected_taxes = round(item.total * (self.LESSON_TAX_RATE / 100), 2)
        self.assertAlmostEqual(item.taxes, expected_taxes, places=2)

        self.gp['registration__buyerPaysSalesTax'] = False

    def test_booking_marks_slot_as_tentative(self):
        '''After initiating a registration-path booking the slot status is tentative.'''
        self.client.force_login(self.nonStaffUser)
        self._book_slot()
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, InstructorAvailabilitySlot.SlotStatus.tentative)

    def test_booking_price_based_on_pricing_tier_and_slot_count(self):
        '''Invoice gross total equals pricingTier.onlinePrice × number of slots booked.'''
        self.client.force_login(self.nonStaffUser)
        self._book_slot(duration=30)  # single 30-minute slot

        invoice_id = self.client.session[REG_VALIDATION_STR]['invoice_id']
        invoice = Invoice.objects.get(id=invoice_id)
        self.assertEqual(invoice.grossTotal, self.defaultPricing.onlinePrice)


# ---------------------------------------------------------------------------
# Booking → no-registration path (allowRegistration=False or no pricing tier)
# ---------------------------------------------------------------------------

class BookingWithoutRegistrationTest(PrivateLessonTestCase):
    '''
    Tests the booking path where allowRegistration=False (or no pricing tier),
    so the user is directed to the lightweight student-info form instead of the
    full registration/payment flow.
    '''

    def test_allow_registration_false_redirects_to_student_info_form(self):
        '''With allowRegistration=False the booking redirects to privateLessonStudentInfo.'''
        self.gp['privateLessons__allowRegistration'] = False
        self.client.force_login(self.nonStaffUser)
        response = self._book_slot()
        self.assertRedirects(
            response, reverse('privateLessonStudentInfo'), fetch_redirect_response=False
        )

    def test_allow_registration_false_sets_session(self):
        '''Session contains a lesson id and expiry after the no-registration booking step.'''
        self.gp['privateLessons__allowRegistration'] = False
        self.client.force_login(self.nonStaffUser)
        self._book_slot()

        session_data = self.client.session.get(PRIVATELESSON_VALIDATION_STR, {})
        self.assertIn('lesson', session_data)
        self.assertIn('expiry', session_data)
        self.assertTrue(PrivateLessonEvent.objects.filter(id=session_data['lesson']).exists())

    def test_student_info_submission_marks_slot_booked(self):
        '''Submitting the student-info form finalizes the lesson and marks slots as booked.'''
        self.gp['privateLessons__allowRegistration'] = False
        self.gp['privateLessons__notifyInstructor'] = False  # isolate slot-status logic
        self.client.force_login(self.nonStaffUser)
        self._book_slot()

        self.client.post(
            reverse('privateLessonStudentInfo'),
            data={
                'firstName': 'Test',
                'lastName': 'Student',
                'email': 'student@test.com',
                'phone': '',
                'agreeToPolicies': True,
            },
        )
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, InstructorAvailabilitySlot.SlotStatus.booked)

    def test_student_info_submission_creates_customer(self):
        '''Submitting the student-info form creates (or updates) a Customer record.'''
        from danceschool.core.models import Customer
        self.gp['privateLessons__allowRegistration'] = False
        self.gp['privateLessons__notifyInstructor'] = False
        self.client.force_login(self.nonStaffUser)
        self._book_slot()

        self.client.post(
            reverse('privateLessonStudentInfo'),
            data={
                'firstName': 'Jane',
                'lastName': 'Doe',
                'email': 'jane@doe.com',
                'phone': '',
                'agreeToPolicies': True,
            },
        )
        self.assertTrue(Customer.objects.filter(email='jane@doe.com').exists())

    def test_no_pricing_tier_redirects_to_student_info_even_with_registration_enabled(self):
        '''A slot without a pricing tier always uses the no-payment path.'''
        self.slot.pricingTier = None
        self.slot.save()
        self.gp['privateLessons__allowRegistration'] = True
        self.client.force_login(self.nonStaffUser)
        response = self._book_slot()
        self.assertRedirects(
            response, reverse('privateLessonStudentInfo'), fetch_redirect_response=False
        )


# ---------------------------------------------------------------------------
# Instructor email notifications
# ---------------------------------------------------------------------------

class InstructorEmailNotificationTest(PrivateLessonTestCase):
    '''
    Tests instructor email notifications triggered by lesson.finalizeBooking().
    Uses mock.patch to intercept email_recipient so the tests are independent
    of the email queue and template rendering infrastructure.
    '''

    def _create_lesson_with_instructor(self):
        '''Create a minimal PrivateLessonEvent linked to the default instructor.'''
        lesson = PrivateLessonEvent.objects.create(
            pricingTier=self.defaultPricing,
            location=self.defaultLocation,
            status=Event.RegStatus.hidden,
        )
        EventStaffMember.objects.create(
            event=lesson,
            category=getConstant('privateLessons__eventStaffCategoryPrivateLesson'),
            staffMember=self.defaultInstructor,
        )
        return lesson

    def _make_instructor_email_template(self):
        '''Create and register a minimal instructor notification template.'''
        template = EmailTemplate.objects.create(
            name='Test Instructor Notification',
            subject='Lesson booked',
            content='A lesson has been scheduled.',
            defaultFromAddress='school@test.com',
            defaultFromName='Test School',
            defaultCC='',
            hideFromForm=True,
        )
        self.gp['privateLessons__lessonBookedInstructorEmailTemplate'] = template
        return template

    def test_finalizeBooking_sends_email_to_instructor(self):
        '''
        When notifyInstructor=True and the template has a from-address and
        content, finalizeBooking() calls email_recipient with the instructor's
        private email address.
        '''
        self._make_instructor_email_template()
        lesson = self._create_lesson_with_instructor()

        with patch('danceschool.core.mixins.EmailRecipientMixin.email_recipient') as mock_send:
            lesson.finalizeBooking(notifyStudent=False)

        # email_recipient should have been called at least once.
        self.assertTrue(mock_send.called)

        # One of the calls must target the instructor's private email.
        to_addresses = [
            call.kwargs.get('to') or (call.args[0] if call.args else None)
            for call in mock_send.call_args_list
        ]
        self.assertIn(self.defaultInstructor.privateEmail, to_addresses)

    def test_finalizeBooking_does_not_email_instructor_when_disabled(self):
        '''When notifyInstructor=False, no instructor email is sent.'''
        self.gp['privateLessons__notifyInstructor'] = False
        self._make_instructor_email_template()
        lesson = self._create_lesson_with_instructor()

        with patch('danceschool.core.mixins.EmailRecipientMixin.email_recipient') as mock_send:
            lesson.finalizeBooking(notifyStudent=False)

        mock_send.assert_not_called()

    def test_full_flow_triggers_finalize_booking(self):
        '''
        End-to-end: completing the student-info form calls finalizeBooking on the lesson.
        '''
        self.gp['privateLessons__allowRegistration'] = False
        self.gp['privateLessons__notifyInstructor'] = False
        self.client.force_login(self.nonStaffUser)
        self._book_slot()

        session_data = self.client.session.get(PRIVATELESSON_VALIDATION_STR, {})
        lesson_id = session_data.get('lesson')

        with patch.object(PrivateLessonEvent, 'finalizeBooking') as mock_finalize:
            self.client.post(
                reverse('privateLessonStudentInfo'),
                data={
                    'firstName': 'Test',
                    'lastName': 'Student',
                    'email': 'student@test.com',
                    'phone': '',
                    'agreeToPolicies': True,
                },
            )

        mock_finalize.assert_called_once()


# ---------------------------------------------------------------------------
# AllowPublicBooking preference
# ---------------------------------------------------------------------------

class AllowPublicBookingTest(PrivateLessonTestCase):
    '''
    Tests that the allowPublicBooking preference controls access to the booking
    page correctly: non-staff users are blocked when disabled, staff users are
    always allowed, and anonymous users are blocked when disabled.
    '''

    def test_public_booking_enabled_allows_non_staff_user(self):
        '''Non-staff users can access the scheduling page when allowPublicBooking=True.'''
        self.gp['privateLessons__allowPublicBooking'] = True
        self.client.force_login(self.nonStaffUser)
        response = self.client.get(reverse('bookPrivateLesson'))
        self.assertEqual(response.status_code, 200)

    def test_public_booking_disabled_blocks_non_staff_user(self):
        '''Non-staff users are redirected to login when allowPublicBooking=False.'''
        self.gp['privateLessons__allowPublicBooking'] = False
        self.client.force_login(self.nonStaffUser)
        response = self.client.get(reverse('bookPrivateLesson'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_public_booking_disabled_still_allows_staff(self):
        '''Staff users (is_staff=True) can always access the scheduling page.'''
        self.gp['privateLessons__allowPublicBooking'] = False
        self.client.force_login(self.superuser)  # superuser has is_staff=True
        response = self.client.get(reverse('bookPrivateLesson'))
        self.assertEqual(response.status_code, 200)

    def test_public_booking_disabled_blocks_anonymous_users(self):
        '''Unauthenticated users are redirected to login when allowPublicBooking=False.'''
        self.gp['privateLessons__allowPublicBooking'] = False
        self.client.logout()
        response = self.client.get(reverse('bookPrivateLesson'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_public_booking_enabled_allows_anonymous_users(self):
        '''Unauthenticated users can view the scheduling page when allowPublicBooking=True.'''
        self.gp['privateLessons__allowPublicBooking'] = True
        self.client.logout()
        response = self.client.get(reverse('bookPrivateLesson'))
        self.assertEqual(response.status_code, 200)
