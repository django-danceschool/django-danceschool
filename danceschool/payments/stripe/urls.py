from django.urls import path

from .views import handle_stripe_checkout, create_checkout_session, SuccessView, CancelledView, webhook

urlpatterns = [
    path('process/', handle_stripe_checkout, name='stripeHandler'),
    path('create-checkout-session/', create_checkout_session, name='stripeSession'),
    path('success/', SuccessView.as_view(), name='stripeSuccess'),
    path('cancelled/', CancelledView.as_view(), name='stripeCanceled'),
    path('webhook/', webhook, name='stripeWebhook'),
]
