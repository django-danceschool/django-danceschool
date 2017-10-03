from django.conf.urls import url

from .stats import popularDiscountsJSON, discountFrequencyJSON

urlpatterns = [
    url(r'^populardiscounts/json/$', popularDiscountsJSON, name='popularDiscountsJSON'),
    url(r'^discountfrequency/json/$', discountFrequencyJSON, name='discountFrequencyJSON'),
]
