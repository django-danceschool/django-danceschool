from django.conf.urls import url

from .views import createPaypalPayment, executePaypalPayment

urlpatterns = [
    url(r'^create_payment/$', createPaypalPayment, name='createPaypalPayment'),
    url(r'^execute_payment/$', executePaypalPayment, name='executePaypalPayment'),
]
