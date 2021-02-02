from django.urls import path

from .views import PayAtDoorView, WillPayAtDoorView

urlpatterns = [
    path('submit/', WillPayAtDoorView.as_view(), name='doorWillPayHandler'),
    path('process/', PayAtDoorView.as_view(), name='doorPaymentHandler'),
]
