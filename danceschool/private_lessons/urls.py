from django.conf.urls import url

from .feeds import json_availability_feed, json_lesson_feed
from .views import BookPrivateLessonView, PrivateLessonStudentInfoView, InstructorAvailabilityView, AddAvailabilitySlotView, UpdateAvailabilitySlotView

urlpatterns = [
    # JSON private lesson availability feeds
    url(r'^availability/feed/json/(?P<instructor_id>[\w\-_]+)/$', json_availability_feed, name='jsonPrivateLessonAvailabilityFeed'),
    url(r'^availability/feed/json/$', json_availability_feed, name='jsonPrivateLessonAvailabilityFeed'),

    # JSON scheduled lesson feeds
    url(r'^scheduled/feed/json/$', json_lesson_feed, name='jsonOwnPrivateLessonFeed'),
    url(r'^scheduled/feed/json/all/$', json_lesson_feed, {'show_others': True}, name='jsonPrivateLessonFeed'),
    url(r'^scheduled/feed/json/(?P<location_id>[0-9]+)/(?P<room_id>[0-9]+)/$', json_lesson_feed, name='jsonOwnPrivateLessonFeed'),
    url(r'^scheduled/feed/json/(?P<location_id>[0-9]+)/(?P<room_id>[0-9]+)/all/$', json_lesson_feed, {'show_others': True}, name='jsonPrivateLessonFeed'),
    url(r'^scheduled/feed/json/(?P<location_id>[0-9]+)/$', json_lesson_feed, name='jsonOwnPrivateLessonFeed'),
    url(r'^scheduled/feed/json/(?P<location_id>[0-9]+)/all/$', json_lesson_feed, {'show_others': True}, name='jsonPrivateLessonFeed'),

    # Views for scheduling a private lesson
    url(r'^schedule/$', BookPrivateLessonView.as_view(), name='bookPrivateLesson'),
    url(r'^schedule/getinfo/$', PrivateLessonStudentInfoView.as_view(), name='privateLessonStudentInfo'),

    # Views for setting instructor availability
    url(r'^instructor/availability/$', InstructorAvailabilityView.as_view(), name='instructorAvailability'),
    url(r'^instructor/availability/add/$', AddAvailabilitySlotView.as_view(), name='addAvailabilitySlot'),
    url(r'^instructor/availability/update/$', UpdateAvailabilitySlotView.as_view(), name='updateAvailabilitySlot'),
]
