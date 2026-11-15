from django.contrib.auth.models import AnonymousUser
from django.template import Context
from django.test import RequestFactory
from django.utils import timezone

from datetime import datetime

from cms.api import add_plugin
from cms.models import Placeholder
from cms.plugin_rendering import ContentRenderer

from ..constants import updateConstant
from ..models import EventSession
from .defaults import DefaultSchoolTestCase


class EventListPluginTest(DefaultSchoolTestCase):
    '''
    The "List of Events" plugin groups events under one or two levels of
    headings, according to the registration organizing rule.  A sorting
    failure in the template is silent (Django's dictsort filter returns an
    empty string), so these tests check that the events are actually listed.
    '''

    def _series(self, month, day, classDescription=None, session=None):
        ''' Create a series next year, so that it is always upcoming. '''
        startTime = timezone.make_aware(
            datetime(timezone.now().year + 1, month, day, 19, 0)
        )
        s = self.create_series(
            startTime=startTime,
            classDescription=classDescription or self.levelOneClassDescription,
        )
        if session:
            s.session = session
            s.save()
        return s

    def _session(self, name):
        return EventSession.objects.create(
            name=name, slug=name.lower().replace(' ', '-')
        )

    def _render(self):
        placeholder = Placeholder.objects.create(slot='test')
        plugin = add_plugin(
            placeholder, 'EventListPlugin', 'en',
            title='Upcoming Classes', eventType='S',
        )
        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        request.session = {}
        request.current_page = None
        renderer = ContentRenderer(request=request)
        return renderer.render_plugin(plugin, Context({'request': request}))

    def test_second_level_grouping_lists_events(self):
        '''
        With two levels of grouping (month, then session), the events are
        listed under their second-level headings, in sorted order (#185).
        '''
        updateConstant('registration__orgRule', 'SessionMonth')
        self._series(
            3, 10, self.levelOneClassDescription, self._session('Session B')
        )
        self._series(
            3, 12, self.levelTwoClassDescription, self._session('Session A')
        )

        html = self._render()

        self.assertIn('March', html)
        self.assertIn(self.levelOneClassDescription.title, html)
        self.assertIn(self.levelTwoClassDescription.title, html)
        self.assertIn('<h5>Session A</h5>', html)
        self.assertIn('<h5>Session B</h5>', html)
        self.assertLess(
            html.index('<h5>Session A</h5>'), html.index('<h5>Session B</h5>')
        )

    def test_month_and_weekday_grouping_lists_events(self):
        ''' Months and weekdays are sorted by number, not by name. '''
        updateConstant('registration__orgRule', 'MonthWeekday')
        april = self._series(4, 10, self.levelOneClassDescription)
        march = self._series(3, 10, self.levelTwoClassDescription)

        html = self._render()

        self.assertIn(april.name, html)
        self.assertIn(march.name, html)
        self.assertLess(html.index('March'), html.index('April'))

    def test_sessions_and_months_can_be_mixed(self):
        '''
        Under the default rule, events with a session are grouped by session
        and other events are grouped by month.  Both must be listed.
        '''
        updateConstant('registration__orgRule', 'SessionFirst')
        self._series(
            3, 10, self.levelOneClassDescription, self._session('Spring Session')
        )
        self._series(4, 10, self.levelTwoClassDescription)

        html = self._render()

        self.assertIn('Spring Session', html)
        self.assertIn(self.levelOneClassDescription.title, html)
        self.assertIn('April', html)
        self.assertIn(self.levelTwoClassDescription.title, html)
