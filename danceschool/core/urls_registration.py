from django.conf.urls import url

from .views import EventRegistrationSummaryView, EventRegistrationSelectView, RefundProcessingView, RefundConfirmationView, ViewInvoiceView, InvoiceNotificationView
from .classreg import RegistrationOfflineView, ClassRegistrationView, SingleClassRegistrationView, ClassRegistrationReferralView,RegistrationSummaryView, StudentInfoView
from .ajax import processCheckIn

urlpatterns = [

    # This view allows the passing of a voucher code in the URL to the class registration page
    # so that Referrers can provide a direct URL to get their referral benefits
    url(r'^$', ClassRegistrationView.as_view(), name='registration'),
    url(r'^id/(?P<marketing_id>[\w\-_]+)/$', ClassRegistrationReferralView.as_view(), name='registrationWithMarketingId'),
    url(r'^referral/(?P<voucher_id>[\w\-_]+)/$', ClassRegistrationReferralView.as_view(), name='registrationWithVoucher'),
    url(r'^event/(?P<uuid>[\w\-_]+)/$', SingleClassRegistrationView.as_view(), name='singleClassRegistration'),

    # This is the view that is redirected to when registration is offline.
    url(r'^offline/$', RegistrationOfflineView.as_view(),name='registrationOffline'),

    # These views handle the remaining steps of the registration process
    url(r'^getinfo/$', StudentInfoView.as_view(), name='getStudentInfo'),
    url(r'^summary/$', RegistrationSummaryView.as_view(), name='showRegSummary'),

    # These are the URLs affiliated with viewing registrations and check-in
    url(r'^registrations/$',EventRegistrationSelectView.as_view(), name='viewregistrations_selectevent'),
    url(r'^registrations/(?P<series_id>[0-9]+)/$', EventRegistrationSummaryView.as_view(), name='viewregistrations'),
    url(r'^registrations/(?P<series_id>[0-9]+)/$', EventRegistrationSummaryView.as_view(), name='viewregistrations'),
    url(r'^registrations/checkin/$', processCheckIn, name='formhandler_checkin'),

    # These URLs are associated with viewing individual invoices and sending notifications
    url(r'^invoice/view/(?P<pk>[0-9a-f-]+)/$', ViewInvoiceView.as_view(), name='viewInvoice'),
    url(r'^invoice/notify/(?P<pk>[0-9a-f-]+)/$', InvoiceNotificationView.as_view(), name='sendInvoiceNotifications'),
    url(r'^invoice/notify/$', InvoiceNotificationView.as_view(), name='sendInvoiceNotifications'),

    # These URLs are for refund processing
    url(r'^invoice/refund/confirm/$', RefundConfirmationView.as_view(), name='refundConfirmation'),
    url(r'^invoice/refund/(?P<pk>[0-9a-f-]+)/$', RefundProcessingView.as_view(), name='refundProcessing'),
]
