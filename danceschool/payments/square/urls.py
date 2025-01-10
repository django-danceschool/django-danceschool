from django.urls import path
from .views import (
    ProcessSquarePaymentView, ProcessPointOfSalePaymentView,
    ViewOrCreateInvoiceView
)

urlpatterns = [
    path(
        'create_payment/', ProcessSquarePaymentView.as_view(),
        name='processSquarePayment'
    ),
    path(
        'process_pointofsale/', ProcessPointOfSalePaymentView.as_view(),
        name='processSquarePointOfSale'
    ),
    path(
        'payment_invoice/<int:pk>/', ViewOrCreateInvoiceView.as_view(),
        name='viewOrCreatePaymentInvoice'
    )
]
