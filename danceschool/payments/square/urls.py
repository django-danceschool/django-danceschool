from django.urls import path
from .views import processSquarePaymentTest, processPointOfSalePayment

urlpatterns = [
    path('create_payment/', processSquarePaymentTest, name='processSquarePayment'),
    path('process_pointofsale/', processPointOfSalePayment, name='processSquarePointOfSale'),
]
