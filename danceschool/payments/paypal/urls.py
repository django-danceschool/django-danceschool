from django.urls import path

from .views import createPaypalOrder, capturePaypalOrder

urlpatterns = [
    path('create_order/', createPaypalOrder, name='createPaypalOrder'),
    path('capture_order/', capturePaypalOrder, name='capturePaypalOrder'),
]
