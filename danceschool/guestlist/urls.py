from django.conf.urls import url

from .views import GuestListView, GuestListJsonView

urlpatterns = [
    url(r'^json/(?P<guestlist_id>[0-9\+]+)/$', GuestListJsonView.as_view(), name='guestListJSON'),
    url(r'^json/(?P<guestlist_id>[0-9\+]+)/(?P<event_id>[0-9\+]+)/$', GuestListJsonView.as_view(), name='guestListJSON'),
    url(r'^(?P<guestlist_id>[0-9\+]+)/$', GuestListView.as_view(), name='viewGuestList'),
    url(r'^(?P<guestlist_id>[0-9\+]+)/(?P<event_id>[0-9\+]+)/$', GuestListView.as_view(), name='viewGuestList'),
]
