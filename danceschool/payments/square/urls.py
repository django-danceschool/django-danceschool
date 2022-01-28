from django.urls import path
from .views import processSquarePayment, processPointOfSalePayment

urlpatterns = [
    path('create_payment/', processSquarePayment, name='processSquarePayment'),
    path('process_pointofsale/', processPointOfSalePayment, name='processSquarePointOfSale'),
]
