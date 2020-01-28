from django.urls import path

from .views import createPaypalPayment, executePaypalPayment

urlpatterns = [
    path('create_payment/', createPaypalPayment, name='createPaypalPayment'),
    path('execute_payment/', executePaypalPayment, name='executePaypalPayment'),
]
