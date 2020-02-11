from django.urls import path

from .views import GiftCertificateCustomizeView, VoucherGenerationView
from .stats import popularVouchersJSON, voucherFrequencyJSON

urlpatterns = [
    path('gift_certificate/customize/', GiftCertificateCustomizeView.as_view(), name='customizeGiftCertificate'),
    path('popularvouchers/json/', popularVouchersJSON, name='popularVouchersJSON'),
    path('voucherfrequency/json/', voucherFrequencyJSON, name='voucherFrequencyJSON'),
    path('generate/', VoucherGenerationView.as_view(), name='generateVoucher'),
]
