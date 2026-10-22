from unittest import mock

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from dynamic_preferences.registries import global_preferences_registry

from danceschool.core.tests.defaults import DefaultSchoolTestCase

from .handlers import checkBanlist
from .models import BannedEmail, BannedPerson, BanFlaggedRecord


class CheckBanlistTest(DefaultSchoolTestCase):
    '''
    The banlist handler must only match on values that were actually provided.
    A missing value (e.g. an email that failed form validation and so is absent
    from cleaned_data) must not match banned people who have no email on file.
    '''

    def setUp(self):
        gp = global_preferences_registry.manager()
        gp['registration__enableBanList'] = True
        gp['registration__banListNotificationEmail'] = 'admin@example.com'

        self.no_email = BannedPerson.objects.create(firstName='Alice', lastName='Banned')
        self.with_email = BannedPerson.objects.create(firstName='Bob', lastName='Banned')
        BannedEmail.objects.create(person=self.with_email, email='bob@banned.test')
        BannedEmail.objects.create(person=self.with_email, email='bob2@banned.test')

        self.request = RequestFactory().get('/')
        self.request.user = User.objects.create_user('plain', 'plain@test.com', 'pass')
        self.request.session = {}

    def _check(self, data):
        '''Returns (flagged, list of sendEmail call args).'''
        with mock.patch('danceschool.banlist.handlers.sendEmail') as send:
            try:
                checkBanlist(sender=None, data=data, request=self.request)
                flagged = False
            except ValidationError:
                flagged = True
        return flagged, send.call_args_list

    def test_unrelated_person_with_valid_data_not_flagged(self):
        flagged, sent = self._check(
            {'firstName': 'merch', 'lastName': 'merch', 'email': 'merch@merch.com'}
        )
        self.assertFalse(flagged)
        self.assertEqual(sent, [])
        self.assertEqual(BanFlaggedRecord.objects.count(), 0)

    def test_missing_email_does_not_match_banned_people_without_emails(self):
        '''Regression: email absent from cleaned_data (None) matched via IS NULL.'''
        flagged, sent = self._check({'firstName': 'merch', 'lastName': 'merch'})
        self.assertFalse(flagged)
        self.assertEqual(sent, [])
        self.assertEqual(BanFlaggedRecord.objects.count(), 0)

    def test_empty_email_is_not_flagged(self):
        flagged, _ = self._check({'firstName': 'merch', 'lastName': 'merch', 'email': ''})
        self.assertFalse(flagged)

    def test_no_data_at_all_is_not_flagged(self):
        flagged, _ = self._check({})
        self.assertFalse(flagged)
        self.assertEqual(BanFlaggedRecord.objects.count(), 0)

    def test_missing_name_does_not_match_on_name(self):
        flagged, _ = self._check({'email': 'someone@else.com'})
        self.assertFalse(flagged)

    def test_name_match_is_flagged_case_insensitively(self):
        flagged, sent = self._check(
            {'firstName': 'alice', 'lastName': 'BANNED', 'email': 'new@person.com'}
        )
        self.assertTrue(flagged)
        self.assertEqual(
            list(BanFlaggedRecord.objects.values_list('person', flat=True)),
            [self.no_email.id]
        )
        self.assertEqual(len(sent), 1)

    def test_name_match_flagged_even_if_email_missing(self):
        flagged, _ = self._check({'firstName': 'Alice', 'lastName': 'Banned'})
        self.assertTrue(flagged)

    def test_email_match_flagged_with_different_name(self):
        flagged, _ = self._check(
            {'firstName': 'Someone', 'lastName': 'Else', 'email': 'BOB@banned.test'}
        )
        self.assertTrue(flagged)
        self.assertEqual(
            list(BanFlaggedRecord.objects.values_list('person', flat=True)),
            [self.with_email.id]
        )

    def test_multiple_banned_emails_do_not_duplicate_flags(self):
        '''A person matching by name and several emails is flagged once.'''
        self._check({'firstName': 'Bob', 'lastName': 'Banned', 'email': 'bob@banned.test'})
        self.assertEqual(BanFlaggedRecord.objects.filter(person=self.with_email).count(), 1)

    def test_notification_reports_every_matched_person(self):
        flagged, sent = self._check(
            {'firstName': 'Alice', 'lastName': 'Banned', 'email': 'bob@banned.test'}
        )
        self.assertTrue(flagged)
        self.assertEqual(BanFlaggedRecord.objects.count(), 2)
        body = str(sent[0][0][1])
        self.assertIn('Alice Banned (matched on name)', body)
        self.assertIn('Bob Banned (matched on email)', body)

    def test_disabled_ban_is_ignored(self):
        self.no_email.disabled = True
        self.no_email.save()
        flagged, _ = self._check({'firstName': 'Alice', 'lastName': 'Banned'})
        self.assertFalse(flagged)
