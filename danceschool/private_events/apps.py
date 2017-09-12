# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse


class PrivateEventsAppConfig(AppConfig):
    name = 'danceschool.private_events'
    verbose_name = _('Private Events Functions')

    def ready(self):
        from danceschool.core.models import Location, Room

        @property
        def jsonPrivateCalendarFeed(self):
            '''
            Makes it easy to get location-specific private calendar
            feeds when looping through locations.
            '''
            return reverse('jsonPrivateCalendarFeed', args=(self.id,))
        Location.add_to_class('jsonPrivateCalendarFeed',jsonPrivateCalendarFeed)

        @property
        def jsonRoomPrivateCalendarFeed(self):
            '''
            Makes it easy to get location-specific private calendar
            feeds when looping through locations.
            '''
            return reverse('jsonPrivateCalendarFeed', args=(self.location.id, self.id,))
        Room.add_to_class('jsonPrivateCalendarFeed',jsonRoomPrivateCalendarFeed)
