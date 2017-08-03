from django.conf.urls import url

from .views import createPaypalHerePayment, executePaypalHerePayment

urlpatterns = [
    url(r'^create_POS_payment/$', createPaypalHerePayment, name='createPaypalHerePayment'),
    url(r'^execute_POS_payment/$', executePaypalHerePayment, name='executePaypalHerePayment'),
]
