from django.urls import path

from .views import BanListView

urlpatterns = [
    path('view-list/', BanListView.as_view(), name='viewBanList'),
]
