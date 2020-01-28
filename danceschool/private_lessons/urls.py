from django.urls import path

from .feeds import json_availability_feed, json_lesson_feed
from .views import (
    BookPrivateLessonView, PrivateLessonStudentInfoView,
    InstructorAvailabilityView, AddAvailabilitySlotView,
    UpdateAvailabilitySlotView
)

urlpatterns = [
    # JSON private lesson availability feeds
    path(
        'availability/feed/json/<slug:instructor_id>/',
        json_availability_feed, name='jsonPrivateLessonAvailabilityFeed'
    ),
    path('availability/feed/json/', json_availability_feed, name='jsonPrivateLessonAvailabilityFeed'),

    # JSON scheduled lesson feeds
    path('scheduled/feed/json/', json_lesson_feed, name='jsonOwnPrivateLessonFeed'),
    path('scheduled/feed/json/all/', json_lesson_feed, {'show_others': True}, name='jsonPrivateLessonFeed'),
    path(
        'scheduled/feed/json/<int:location_id>/<int:room_id>/',
        json_lesson_feed, name='jsonOwnPrivateLessonFeed'
    ),
    path(
        'scheduled/feed/json/<int:location_id>/<int:room_id>/all/$',
        json_lesson_feed, {'show_others': True}, name='jsonPrivateLessonFeed'
    ),
    path('scheduled/feed/json/<int:location_id>/', json_lesson_feed, name='jsonOwnPrivateLessonFeed'),
    path(
        'scheduled/feed/json/<int:location_id>/all/',
        json_lesson_feed, {'show_others': True}, name='jsonPrivateLessonFeed'
    ),

    # Views for scheduling a private lesson
    path('schedule/', BookPrivateLessonView.as_view(), name='bookPrivateLesson'),
    path('schedule/getinfo/', PrivateLessonStudentInfoView.as_view(), name='privateLessonStudentInfo'),

    # Views for setting instructor availability
    path('instructor/availability/', InstructorAvailabilityView.as_view(), name='instructorAvailability'),
    path('instructor/availability/add/', AddAvailabilitySlotView.as_view(), name='addAvailabilitySlot'),
    path('instructor/availability/update/', UpdateAvailabilitySlotView.as_view(), name='updateAvailabilitySlot'),
]
