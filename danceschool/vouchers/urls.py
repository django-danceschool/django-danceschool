from django.conf.urls import url

from .views import GiftCertificateCustomizeView

urlpatterns = [
    url(r'^gift_certificate/customize/$', GiftCertificateCustomizeView.as_view(), name='customizeGiftCertificate'),
]
