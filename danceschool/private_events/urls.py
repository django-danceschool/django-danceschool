from django.urls import path

from .feeds import EventFeed, json_event_feed
from .views import addPrivateEvent, PrivateCalendarView

urlpatterns = [
    # These are the calendar feeds.
    path('feed/json/', json_event_feed, name='jsonPrivateCalendarFeed'),
    path(
        'feed/json/location/<int:location_id>/<int:room_id>/',
        json_event_feed, name='jsonPrivateCalendarFeed'
    ),
    path('feed/json/location/<int:location_id>/', json_event_feed, name='jsonPrivateCalendarFeed'),
    path('feed/<slug:instructorFeedKey>/', EventFeed(), name='privateCalendarFeed'),

    path('calendar/', PrivateCalendarView.as_view(), name='privateCalendar'),

    path('add/', addPrivateEvent, name='addPrivateEvent'),
]
