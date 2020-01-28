from django.urls import path

from .views import handle_payatdoor, handle_willpayatdoor

urlpatterns = [
    path('submit/', handle_willpayatdoor, name='doorWillPayHandler'),
    path('process/', handle_payatdoor, name='doorPaymentHandler'),
]
