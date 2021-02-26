from django.urls import path, re_path
from django.contrib import admin

from .feeds import EventFeed, json_event_feed
from .views import (
    SubmissionRedirectView, InstructorStatsView, OtherInstructorStatsView,
    IndividualClassView, IndividualPublicEventView, StaffDirectoryView,
    EmailConfirmationView, SendEmailView, SubstituteReportingView,
    StaffMemberBioChangeView, AccountProfileView, OtherAccountProfileView,
    RepeatEventsView, IndividualClassReferralView, IndividualPublicEventReferralView,
    RefundProcessingView, RefundConfirmationView, ViewInvoiceView,
    InvoiceNotificationView
)
from .ajax import UserAccountInfo, updateSeriesAttributes, getEmailTemplate
from .autocomplete_light_registry import (
    CustomerAutoComplete, UserAutoComplete, StaffMemberAutoComplete,
    EventAutoComplete, ClassDescriptionAutoComplete
)

admin.autodiscover()

urlpatterns = [
    # These URLs are for Ajax and autocomplete functionality
    path('staff/substitute/filter/', updateSeriesAttributes, name='ajaxhandler_submitsubstitutefilter'),
    path('staff/sendemail/template/', getEmailTemplate, name='ajaxhandler_getemailtemplate'),
    path('staff/autocomplete/user', UserAutoComplete.as_view(), name='autocompleteUser'),
    path('staff/autocomplete/customer', CustomerAutoComplete.as_view(), name='autocompleteCustomer'),
    path(
        'staff/autocomplete/classdescription',
        ClassDescriptionAutoComplete.as_view(),
        name='autocompleteClassDescription'
    ),
    path(
        'staff/autocomplete/staffmember',
        StaffMemberAutoComplete.as_view(create_field='fullName'),
        name='autocompleteStaffMember'
    ),
    path('staff/autocomplete/event', EventAutoComplete.as_view(), name='autocompleteEvent'),
    path(
        'staff/autocomplete/classdescription',
        ClassDescriptionAutoComplete.as_view(),
        name='autocompleteClassDescription'
    ),
    path('accounts/info/', UserAccountInfo.as_view(), name='getUserAccountInfo'),

    # For general admin form submission redirects
    path('form/submitted/', SubmissionRedirectView.as_view(), name='submissionRedirect'),

    path('staff/directory/', StaffDirectoryView.as_view(), name='staffDirectory'),
    path('staff/sendemail/', SendEmailView.as_view(), name='emailStudents'),
    path('staff/sendemail/confirm/', EmailConfirmationView.as_view(), name='emailConfirmation'),
    path('staff/substitute/', SubstituteReportingView.as_view(), name='substituteTeacherForm'),

    # These provide the ability to view one's own stats or another instructor's stats
    re_path(
        r'^staff/instructor-stats/(?P<first_name>[\w\+\.]+)-(?P<last_name>[\w\+\.]+)/$',
        OtherInstructorStatsView.as_view(), name='staffMemberStats'
    ),
    path('staff/instructor-stats/', InstructorStatsView.as_view(), name='staffMemberStats'),

    # This provides the ability to edit one's own bio
    path('staff/bio/', StaffMemberBioChangeView.as_view(), name='staffBioChange'),

    # These are for the calendar feeds
    path('events/feed/', EventFeed(), name='calendarFeed'),
    path('events/feed/json/', json_event_feed, name='jsonCalendarFeed'),
    path('events/feed/<slug:instructorFeedKey>/', EventFeed(), name='calendarFeed'),
    path(
        'events/feed/json/location/<int:locationId>/<int:roomId>/',
        json_event_feed, name='jsonCalendarLocationFeed'
    ),
    path('events/feed/json/location/<int:locationId>/', json_event_feed, name='jsonCalendarLocationFeed'),
    path('events/feed/json/<slug:instructorFeedKey>/', json_event_feed, name='jsonCalendarFeed'),

    # This allows creation of duplicate offset events from admin
    path('events/repeat/', RepeatEventsView.as_view(), name='repeatEvents'),

    # These are for individual class views and event views
    path('classes/<int:year>/<slug:month>/<slug:slug>/', IndividualClassView.as_view(), name='classView'),
    path('events/<int:year>/<slug:month>/<slug:slug>/', IndividualPublicEventView.as_view(), name='eventView'),
    path('classes/<slug:session_slug>/<slug:slug>/', IndividualClassView.as_view(), name='classViewSession'),
    path('events/<slug:session_slug>/<slug:slug>/', IndividualPublicEventView.as_view(), name='eventViewSession'),
    path(
        'classes/<slug:session_slug>/<int:year>/<slug:month>/<slug:slug>/',
        IndividualClassView.as_view(), name='classViewSessionMonth'
    ),
    path(
        'events/<slug:session_slug>/<int:year>/<slug:month>/<slug:slug>/',
        IndividualPublicEventView.as_view(), name='eventViewSessionMonth'
    ),

    # Pass along a marketing ID to an individual event view
    path(
        'classes/<int:year>/<slug:month>/<slug:slug>/id/<slug:marketing_id>/',
        IndividualClassReferralView.as_view(), name='classReferralView'
    ),
    path(
        'events/<int:year>/<slug:month>/<slug:slug>/id/<slug:marketing_id>/',
        IndividualPublicEventReferralView.as_view(), name='eventReferralView'
    ),
    path(
        'classes/<slug:session_slug>/<slug:slug>/id/<slug:marketing_id>/',
        IndividualClassReferralView.as_view(), name='classReferralViewSession'
    ),
    path(
        'events/<slug:session_slug>/<slug:slug>/id/<slug:marketing_id>/',
        IndividualPublicEventReferralView.as_view(), name='eventReferralViewSession'
    ),
    path(
        'classes/<slug:session_slug>/<int:year>/<slug:month>/<slug:slug>/id/<slug:marketing_id>/',
        IndividualClassReferralView.as_view(), name='classReferralViewSessionMonth'
    ),
    path(
        'events/<slug:session_slug>/<int:year>/<slug:month>/<slug:slug>/id/<slug:marketing_id>/',
        IndividualPublicEventReferralView.as_view(), name='eventReferralViewSessionMonth'
    ),

    # Pass along a voucher ID to an individual event view
    path(
        'classes/<int:year>/<slug:month>/<slug:slug>/referral/<slug:voucher_id>/',
        IndividualClassReferralView.as_view(), name='classReferralView'
    ),
    path(
        'events/<int:year>/<slug:month>/<slug:slug>/referral/<slug:voucher_id>/',
        IndividualPublicEventReferralView.as_view(), name='eventReferralView'
    ),
    path(
        'classes/<slug:session_slug>/<slug:slug>/referral/<slug:voucher_id>/',
        IndividualClassReferralView.as_view(), name='classReferralViewSession'
    ),
    path(
        'events/<slug:session_slug>/<slug:slug>/referral/<slug:voucher_id>/',
        IndividualPublicEventReferralView.as_view(), name='eventReferralViewSession'
    ),
    path(
        'classes/<slug:session_slug>/<int:year>/<slug:month>/<slug:slug>/referral/<slug:voucher_id>/',
        IndividualClassReferralView.as_view(), name='classReferralViewSessionMonth'
    ),
    path(
        'events/<slug:session_slug>/<int:year>/<slug:month>/<slug:slug>/referral/<slug:voucher_id>/',
        IndividualPublicEventReferralView.as_view(), name='eventReferralViewSessionMonth'
    ),

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

    # User profiles
    path('accounts/profile/<int:user_id>/', OtherAccountProfileView.as_view(), name='accountProfile'),
    path('accounts/profile/', AccountProfileView.as_view(), name='accountProfile'),

]
