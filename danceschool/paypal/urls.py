from django.conf.urls import url

from .views import payment_received

urlpatterns = [
    url(r'^payment_received/$', payment_received, name='payment_received'),
]
