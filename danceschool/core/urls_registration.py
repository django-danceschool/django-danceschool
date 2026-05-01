from django.urls import path

from .views.registration_summary import EventRegistrationSummaryView, EventRegistrationSelectView, EventRegistrationJsonView
from .views.checkin import CustomerSingleCheckInView, CustomerQrCodeView, SchoolSingleCheckInView, ProcessCheckInView
from .views.cart import PurchasableItemsView, CartView, CartSummaryView
from .views.registration import RegistrationOfflineView, PublicRegisterView, RegistrationSummaryView, StudentInfoView, MultiRegCustomerNameView, PartnerRequiredView

urlpatterns = [
    # Public-facing registration page and referral variants
    path('', PublicRegisterView.as_view(), name='registration'),
    path(
        'referral/<slug:voucher_id>/',
        PublicRegisterView.as_view(),
        name='registrationWithVoucher',
    ),
    path(
        'id/<slug:marketing_id>/',
        PublicRegisterView.as_view(),
        name='registrationWithMarketingId',
    ),

    path('api/', PurchasableItemsView.as_view(), name='purchasableItems'),
    path('cart/', CartView.as_view(), name='cart'),
    path('cart/summary/', CartSummaryView.as_view(), name='cartSummary'),

    # This is the view that is redirected to when registration is offline.
    path('offline/', RegistrationOfflineView.as_view(), name='registrationOffline'),

    # These views handle the remaining steps of the registration process
    path('getinfo/', StudentInfoView.as_view(), name='getStudentInfo'),
    path('getinfo/names/', MultiRegCustomerNameView.as_view(), name='multiRegNameInfo'),
    path('getinfo/partners/', PartnerRequiredView.as_view(), name='partnerRequiredForm'),
    path('summary/', RegistrationSummaryView.as_view(), name='showRegSummary'),

    # These are the URLs affiliated with viewing registrations and check-in
    path('viewregistrations/', EventRegistrationSelectView.as_view(), name='viewregistrations_selectevent'),
    path(
        'viewregistrations/<int:event_id>/',
        EventRegistrationSummaryView.as_view(), name='viewregistrations'
    ),
    path(
        'check-in/show/<uuid:invoice_id>/',
        CustomerSingleCheckInView.as_view(), name='customer_checkin'
    ),
    path(
        'check-in/show/<uuid:invoice_id>/<str:validation_string>/',
        CustomerSingleCheckInView.as_view(), name='customer_checkin_validated'
    ),
    path('check-in/qr/<uuid:invoice_id>/', CustomerQrCodeView.as_view(), name='customer_qrcode'),
    path(
        'check-in/qr/<uuid:invoice_id>/<str:validation_string>/',
        CustomerQrCodeView.as_view(), name='customer_qrcode_validated'
    ),
    path(
        'check-in/process/<uuid:pk>/',
        SchoolSingleCheckInView.as_view(), name='school_checkin'
    ),
    path('registrations/json/', EventRegistrationJsonView.as_view(), name='viewregistrations_json'),
    path('registrations/checkin/', ProcessCheckInView.as_view(), name='ajax_checkin'),

]
