from django.test import TestCase
from django.dispatch import Signal


class HeaderStatsSignalTest(TestCase):
    """
    Tests that the get_registration_summary_header_stats signal is declared
    in danceschool.core.signals and is a Signal instance.
    """

    def test_signal_is_declared(self):
        from danceschool.core.signals import get_registration_summary_header_stats
        self.assertIsInstance(get_registration_summary_header_stats, Signal)


from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from django.dispatch import receiver
from django.contrib.auth.models import User

from danceschool.core.models import Event, PublicEvent, EventOccurrence
from danceschool.core.signals import get_registration_summary_header_stats
from danceschool.core.views.registration_summary import EventRegistrationSummaryView


class HeaderStatsViewIntegrationTest(TestCase):
    """
    Tests that EventRegistrationSummaryView fires the signal with the
    expected kwargs and merges returned dicts into extra_header_stats.
    """

    def setUp(self):
        now = timezone.now()
        self.superuser = User.objects.create_superuser(
            'testuser', 'test@example.com', 'pass'
        )
        self.event = PublicEvent.objects.create(
            title='Test Social',
            slug='test-social',
            status=Event.RegStatus.enabled,
        )
        EventOccurrence.objects.create(
            event=self.event,
            startTime=now + timedelta(days=1),
            endTime=now + timedelta(days=1, hours=2),
        )
        self.client.login(username='testuser', password='pass')

    def test_no_receivers_yields_empty_header_stats(self):
        response = self.client.get(
            reverse('viewregistrations', args=(self.event.id,))
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['extra_header_stats'], [])

    def test_single_receiver_populates_header_stats(self):
        @receiver(
            get_registration_summary_header_stats,
            dispatch_uid='test_single_receiver',
        )
        def contributor(sender, event, registrations, **kwargs):
            return [{'label': 'Test Stat', 'value': 42}]

        try:
            response = self.client.get(
                reverse('viewregistrations', args=(self.event.id,))
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.context['extra_header_stats'],
                [{'label': 'Test Stat', 'value': 42}],
            )
        finally:
            get_registration_summary_header_stats.disconnect(
                dispatch_uid='test_single_receiver',
            )

    def test_multiple_receivers_are_concatenated(self):
        @receiver(
            get_registration_summary_header_stats,
            dispatch_uid='test_multi_a',
        )
        def contributor_a(sender, event, registrations, **kwargs):
            return [{'label': 'A', 'value': 1}]

        @receiver(
            get_registration_summary_header_stats,
            dispatch_uid='test_multi_b',
        )
        def contributor_b(sender, event, registrations, **kwargs):
            return [{'label': 'B', 'value': 2}]

        try:
            response = self.client.get(
                reverse('viewregistrations', args=(self.event.id,))
            )
            labels = [s['label'] for s in response.context['extra_header_stats']]
            self.assertIn('A', labels)
            self.assertIn('B', labels)
            self.assertEqual(len(response.context['extra_header_stats']), 2)
        finally:
            get_registration_summary_header_stats.disconnect(
                dispatch_uid='test_multi_a',
            )
            get_registration_summary_header_stats.disconnect(
                dispatch_uid='test_multi_b',
            )

    def test_receiver_returning_empty_list_contributes_nothing(self):
        @receiver(
            get_registration_summary_header_stats,
            dispatch_uid='test_empty_receiver',
        )
        def contributor(sender, event, registrations, **kwargs):
            return []

        try:
            response = self.client.get(
                reverse('viewregistrations', args=(self.event.id,))
            )
            self.assertEqual(response.context['extra_header_stats'], [])
        finally:
            get_registration_summary_header_stats.disconnect(
                dispatch_uid='test_empty_receiver',
            )

    def test_signal_receives_event_and_registrations_kwargs(self):
        seen = {}

        @receiver(
            get_registration_summary_header_stats,
            dispatch_uid='test_kwargs_receiver',
        )
        def contributor(sender, event, registrations, **kwargs):
            seen['sender'] = sender
            seen['event_id'] = event.id
            seen['registrations_is_iterable'] = hasattr(registrations, '__iter__')
            return []

        try:
            self.client.get(
                reverse('viewregistrations', args=(self.event.id,))
            )
            self.assertEqual(seen['sender'], EventRegistrationSummaryView)
            self.assertEqual(seen['event_id'], self.event.id)
            self.assertTrue(seen['registrations_is_iterable'])
        finally:
            get_registration_summary_header_stats.disconnect(
                dispatch_uid='test_kwargs_receiver',
            )
