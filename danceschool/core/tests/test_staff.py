
from django.urls import reverse

from ..models import EventStaffMember
from ..constants import getConstant
from .defaults import DefaultSchoolTestCase


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
                'event': s.id, 'occurrences': s.eventoccurrence_set.values_list('id', flat=True),
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