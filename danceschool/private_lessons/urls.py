from django.conf.urls import url

from .feeds import json_availability_feed
from .views import BookPrivateLessonView, InstructorAvailabilityView, AddAvailabilitySlotView, UpdateAvailabilitySlotView

urlpatterns = [
    # These are the calendar feeds.  They all require an instructor's feed key to keep things private.
    url(r'^feed/json/(?P<instructor_id>[\w\-_]+)/$', json_availability_feed, name='jsonPrivateLessonAvailabilityFeed'),
    url(r'^feed/json/$', json_availability_feed, name='jsonPrivateLessonAvailabilityFeed'),

    url(r'^schedule/$', BookPrivateLessonView.as_view(), name='bookPrivateLesson'),

    url(r'^instructor/availability/$', InstructorAvailabilityView.as_view(), name='instructorAvailability'),
    url(r'^instructor/availability/add/$', AddAvailabilitySlotView.as_view(), name='addAvailabilitySlot'),
    url(r'^instructor/availability/update/$', UpdateAvailabilitySlotView.as_view(), name='updateAvailabilitySlot'),
]
