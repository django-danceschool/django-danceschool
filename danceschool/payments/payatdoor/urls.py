from django.conf.urls import url

from .views import handle_payatdoor, handle_willpayatdoor

urlpatterns = [
    url(r'^submit/$', handle_willpayatdoor, name='doorWillPayHandler'),
    url(r'^process/$', handle_payatdoor, name='doorPaymentHandler'),
]
