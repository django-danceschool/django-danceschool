from django.urls import path

from .stats import popularDiscountsJSON, discountFrequencyJSON

urlpatterns = [
    path('populardiscounts/json/', popularDiscountsJSON, name='popularDiscountsJSON'),
    path('discountfrequency/json/', discountFrequencyJSON, name='discountFrequencyJSON'),
]
