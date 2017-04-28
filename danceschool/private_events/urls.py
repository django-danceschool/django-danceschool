from django.conf.urls import url

from .feeds import EventFeed, json_event_feed
from .views import addPrivateEvent, PrivateCalendarView

urlpatterns = [
    # These are the calendar feeds.  They all require an instructor's feed key to keep things private.
    url(r'^feed/(?P<instructorFeedKey>[\w\-_]+)/$', EventFeed(), name='privateCalendarFeed'),
    url(r'^feed/json/(?P<instructorFeedKey>[\w\-_]+)/$', json_event_feed, name='jsonPrivateCalendarFeed'),

    url(r'^calendar/$', PrivateCalendarView.as_view(), name='privateCalendar'),

    url(r'^add/$',addPrivateEvent,name='addPrivateEvent'),
]
