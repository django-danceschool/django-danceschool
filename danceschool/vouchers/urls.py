from django.conf.urls import url

from .views import GiftCertificateCustomizeView
from .stats import popularVouchersJSON, voucherFrequencyJSON

urlpatterns = [
    url(r'^gift_certificate/customize/$', GiftCertificateCustomizeView.as_view(), name='customizeGiftCertificate'),
    url(r'^popularvouchers/json/$', popularVouchersJSON, name='popularVouchersJSON'),
    url(r'^voucherfrequency/json/$', voucherFrequencyJSON, name='voucherFrequencyJSON'),
]
