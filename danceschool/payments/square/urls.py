from django.conf.urls import url
from .views import processSquarePayment, processPointOfSalePayment

urlpatterns = [
    url(r'^create_payment/$', processSquarePayment, name='processSquarePayment'),
    url(r'^process_pointofsale/$', processPointOfSalePayment, name='processSquarePointOfSale'),
]
