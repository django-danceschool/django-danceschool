from django.urls import path

from .views import handle_stripe_checkout

urlpatterns = [
    path('process/', handle_stripe_checkout, name='stripeHandler'),
]
