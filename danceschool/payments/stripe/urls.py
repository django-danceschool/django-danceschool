from django.urls import path

from .views import create_checkout_session, stripe_return, SuccessView, CancelledView, webhook

urlpatterns = [
    path('create-checkout-session/', create_checkout_session, name='stripeSession'),
    path('return/', stripe_return, name='stripeReturn'),
    path('success/', SuccessView.as_view(), name='stripeSuccess'),
    path('cancelled/', CancelledView.as_view(), name='stripeCanceled'),
    path('webhook/', webhook, name='stripeWebhook'),
]
