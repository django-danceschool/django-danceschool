from django.conf.urls import url
from .views import processSquarePayment

urlpatterns = [
    url(r'^create_payment/$', processSquarePayment, name='processSquarePayment'),
]
