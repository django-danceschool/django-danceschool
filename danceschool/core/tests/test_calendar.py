from django.urls import reverse

from datetime import timedelta
import dateutil.parser

from .defaults import DefaultSchoolTestCase


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
