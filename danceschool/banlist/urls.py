from django.conf.urls import url

from .views import BanListView

urlpatterns = [
    url(r'^view-list/$', BanListView.as_view(), name='viewBanList'),
]
