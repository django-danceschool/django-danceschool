from django.urls import path
from .views import ProcessSquarePaymentView, ProcessPointOfSalePaymentView

urlpatterns = [
    path('create_payment/', ProcessSquarePaymentView.as_view(), name='processSquarePayment'),
    path('process_pointofsale/', ProcessPointOfSalePaymentView.as_view(), name='processSquarePointOfSale'),
]
