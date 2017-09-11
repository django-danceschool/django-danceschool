from django.conf.urls import url

from .feeds import EventFeed, json_event_feed
from .views import addPrivateEvent, PrivateCalendarView

urlpatterns = [
    # These are the calendar feeds.
    url(r'^feed/json/$', json_event_feed, name='jsonPrivateCalendarFeed'),
    url(r'^feed/json/location/(?P<location_id>[0-9]+)/(?P<room_id>[0-9]+)/$', json_event_feed, name='jsonPrivateCalendarFeed'),
    url(r'^feed/json/location/(?P<location_id>[0-9]+)/$', json_event_feed, name='jsonPrivateCalendarFeed'),
    url(r'^feed/(?P<instructorFeedKey>[\w\-_]+)/$', EventFeed(), name='privateCalendarFeed'),

    url(r'^calendar/$', PrivateCalendarView.as_view(), name='privateCalendar'),

    url(r'^add/$',addPrivateEvent,name='addPrivateEvent'),
]
