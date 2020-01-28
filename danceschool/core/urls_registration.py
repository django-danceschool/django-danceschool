from django.urls import path

from .views import (
    EventRegistrationSummaryView, EventRegistrationSelectView,
    EventRegistrationJsonView, RefundProcessingView, RefundConfirmationView,
    ViewInvoiceView, InvoiceNotificationView
)
from .classreg import (
    RegistrationOfflineView, ClassRegistrationView, SingleClassRegistrationView,
    ClassRegistrationReferralView, RegistrationSummaryView, StudentInfoView,
    AjaxClassRegistrationView, SingleClassRegistrationReferralView
)
from .ajax import ProcessCheckInView

urlpatterns = [

    # This view allows the passing of a voucher code in the URL to the class registration page
    # so that Referrers can provide a direct URL to get their referral benefits
    path('', ClassRegistrationView.as_view(), name='registration'),
    path('ajax/', AjaxClassRegistrationView.as_view(), name='ajaxRegistration'),
    path(
        'id/<slug:marketing_id>/',
        ClassRegistrationReferralView.as_view(),
        name='registrationWithMarketingId'
    ),
    path(
        'referral/<slug:voucher_id>/',
        ClassRegistrationReferralView.as_view(),
        name='registrationWithVoucher'
    ),
    path(
        'event/<uuid:uuid>/',
        SingleClassRegistrationView.as_view(),
        name='singleClassRegistration'
    ),
    path(
        'event/<uuid:uuid>/id/<slug:marketing_id>/',
        SingleClassRegistrationReferralView.as_view(),
        name='singleClassReferralRegistration'
    ),
    path(
        'event/<uuid:uuid>/referral/<slug:voucher_id>/',
        SingleClassRegistrationReferralView.as_view(),
        name='singleClassReferralRegistration'
    ),

    # This is the view that is redirected to when registration is offline.
    path('offline/', RegistrationOfflineView.as_view(), name='registrationOffline'),

    # These views handle the remaining steps of the registration process
    path('getinfo/', StudentInfoView.as_view(), name='getStudentInfo'),
    path('summary/', RegistrationSummaryView.as_view(), name='showRegSummary'),

    # These are the URLs affiliated with viewing registrations and check-in
    path('registrations/', EventRegistrationSelectView.as_view(), name='viewregistrations_selectevent'),
    path(
        'registrations/<int:event_id>/',
        EventRegistrationSummaryView.as_view(), name='viewregistrations'
    ),
    path('registrations/json/', EventRegistrationJsonView.as_view(), name='viewregistrations_json'),
    path('registrations/checkin/', ProcessCheckInView.as_view(), name='ajax_checkin'),


    # These URLs are associated with viewing individual invoices and sending notifications
    path('invoice/view/<uuid:pk>/', ViewInvoiceView.as_view(), name='viewInvoice'),
    path(
        'invoice/notify/<uuid:pk>/',
        InvoiceNotificationView.as_view(), name='sendInvoiceNotifications'
    ),
    path('invoice/notify/', InvoiceNotificationView.as_view(), name='sendInvoiceNotifications'),

    # These URLs are for refund processing
    path('invoice/refund/confirm/', RefundConfirmationView.as_view(), name='refundConfirmation'),
    path('invoice/refund/<uuid:pk>/', RefundProcessingView.as_view(), name='refundProcessing'),
]
