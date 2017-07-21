from django.conf.urls import url

from .views import handle_stripe_checkout

urlpatterns = [
    url(r'^process/$', handle_stripe_checkout, name='stripeHandler'),
]
