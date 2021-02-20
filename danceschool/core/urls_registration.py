from django.urls import path

from .views import (
    EventRegistrationSummaryView, EventRegistrationSelectView,
    EventRegistrationJsonView, 
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
    path('viewregistrations/', EventRegistrationSelectView.as_view(), name='viewregistrations_selectevent'),
    path(
        'viewregistrations/<int:event_id>/',
        EventRegistrationSummaryView.as_view(), name='viewregistrations'
    ),
    path('registrations/json/', EventRegistrationJsonView.as_view(), name='viewregistrations_json'),
    path('registrations/checkin/', ProcessCheckInView.as_view(), name='ajax_checkin'),

]
