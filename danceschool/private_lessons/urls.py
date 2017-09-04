from django.conf.urls import url

from .feeds import json_availability_feed, json_scheduled_feed
from .views import BookPrivateLessonView, PrivateLessonStudentInfoView, InstructorAvailabilityView, AddAvailabilitySlotView, UpdateAvailabilitySlotView

urlpatterns = [
    url(r'^availability/feed/json/(?P<instructor_id>[\w\-_]+)/$', json_availability_feed, name='jsonPrivateLessonAvailabilityFeed'),
    url(r'^availability/feed/json/$', json_availability_feed, name='jsonPrivateLessonAvailabilityFeed'),

    # This requires a feedKey to be passed to keep things private.
    url(r'^scheduled/feed/json/(?P<instructorFeedKey>[\w\-_]+)/$', json_scheduled_feed, name='jsonPrivateLessonScheduledFeed'),

    url(r'^schedule/$', BookPrivateLessonView.as_view(), name='bookPrivateLesson'),
    url(r'^schedule/getinfo/$', PrivateLessonStudentInfoView.as_view(), name='privateLessonStudentInfo'),

    url(r'^instructor/availability/$', InstructorAvailabilityView.as_view(), name='instructorAvailability'),
    url(r'^instructor/availability/add/$', AddAvailabilitySlotView.as_view(), name='addAvailabilitySlot'),
    url(r'^instructor/availability/update/$', UpdateAvailabilitySlotView.as_view(), name='updateAvailabilitySlot'),
]
