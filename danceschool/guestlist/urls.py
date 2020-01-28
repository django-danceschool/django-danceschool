from django.urls import path

from .views import GuestListView, GuestListJsonView

urlpatterns = [
    path('json/<int:guestlist_id>/', GuestListJsonView.as_view(), name='guestListJSON'),
    path(
        'json/<int:guestlist_id>/<int:event_id>/',
        GuestListJsonView.as_view(), name='guestListJSON'
    ),
    path('<int:guestlist_id>/', GuestListView.as_view(), name='viewGuestList'),
    path(
        '<int:guestlist_id>/<int:event_id>/',
        GuestListView.as_view(), name='viewGuestList'
    ),
]
