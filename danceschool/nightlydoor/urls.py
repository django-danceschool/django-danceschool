from django.conf.urls import url

from .views import NightlyRegisterView

urlpatterns = [
    url(r'^register/(?P<year>[0-9]+)/(?P<month>[0-9]+)/(?P<day>[0-9]+)/$', NightlyRegisterView.as_view(), name='nightlyRegister'),
]
