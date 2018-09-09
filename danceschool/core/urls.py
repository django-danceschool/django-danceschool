from django.conf.urls import url
from django.contrib import admin

from .feeds import EventFeed, json_event_feed
from .views import SubmissionRedirectView, InstructorStatsView, OtherInstructorStatsView, IndividualClassView, IndividualEventView, StaffDirectoryView, EmailConfirmationView, SendEmailView, SubstituteReportingView, InstructorBioChangeView, AccountProfileView, OtherAccountProfileView, RepeatEventsView
from .ajax import UserAccountInfo, updateSeriesAttributes, getEmailTemplate
from .autocomplete_light_registry import CustomerAutoComplete, UserAutoComplete

admin.autodiscover()

urlpatterns = [
    # These URLs are for Ajax and autocomplete functionality
    url(r'^staff/substitute/filter/$', updateSeriesAttributes, name='ajaxhandler_submitsubstitutefilter'),
    url(r'^staff/sendemail/template/$', getEmailTemplate, name='ajaxhandler_getemailtemplate'),
    url(r'^staff/autocomplete/user', UserAutoComplete.as_view(), name='autocompleteUser'),
    url(r'^staff/autocomplete/customer', CustomerAutoComplete.as_view(), name='autocompleteCustomer'),
    url(r'^accounts/info/$', UserAccountInfo.as_view(), name='getUserAccountInfo'),

    # For general admin form submission redirects
    url(r'^form/submitted/$', SubmissionRedirectView.as_view(), name='submissionRedirect'),

    url(r'^staff/directory/$',StaffDirectoryView.as_view(),name='staffDirectory'),
    url(r'^staff/sendemail/$', SendEmailView.as_view(),name='emailStudents'),
    url(r'^staff/sendemail/confirm/$', EmailConfirmationView.as_view(),name='emailConfirmation'),
    url(r'^staff/substitute/$', SubstituteReportingView.as_view(),name='substituteTeacherForm'),

    # These provide the ability to view one's own stats or another instructor's stats
    url(r'^staff/instructor-stats/(?P<first_name>[\w\+\.]+)-(?P<last_name>[\w\+\.]+)/$', OtherInstructorStatsView.as_view(), name='instructorStats'),
    url(r'^staff/instructor-stats/$', InstructorStatsView.as_view(), name='instructorStats'),

    # This provides the ability to edit one's own bio
    url(r'^staff/bio/$', InstructorBioChangeView.as_view(), name='instructorBioChange'),

    # These are for the calendar feeds
    url(r'^events/feed/$', EventFeed(), name='calendarFeed'),
    url(r'^events/feed/json/$', json_event_feed, name='jsonCalendarFeed'),
    url(r'^events/feed/(?P<instructorFeedKey>[\w\-_]+)/$', EventFeed(), name='calendarFeed'),
    url(r'^events/feed/json/location/(?P<locationId>[0-9]+)/(?P<roomId>[0-9]+)$', json_event_feed, name='jsonCalendarLocationFeed'),
    url(r'^events/feed/json/location/(?P<locationId>[0-9]+)/$', json_event_feed, name='jsonCalendarLocationFeed'),
    url(r'^events/feed/json/(?P<instructorFeedKey>[\w\-_]+)/$', json_event_feed, name='jsonCalendarFeed'),

    # This allows creation of duplicate offset events from admin
    url(r'^events/repeat/$',RepeatEventsView.as_view(),name='repeatEvents'),

    # These are for individual class views and event views
    url(r'^classes/(?P<year>[0-9]+)/(?P<month>[\w]+)/(?P<slug>[\w\-_]+)/$', IndividualClassView.as_view(), name='classView'),
    url(r'^events/(?P<year>[0-9]+)/(?P<month>[\w]+)/(?P<slug>[\w\-_]+)/$', IndividualEventView.as_view(), name='eventView'),
    url(r'^classes/(?P<session_slug>[\w\-_]+)/(?P<slug>[\w\-_]+)/$', IndividualClassView.as_view(), name='classViewSession'),
    url(r'^events/(?P<session_slug>[\w\-_]+)/(?P<slug>[\w\-_]+)/$', IndividualEventView.as_view(), name='eventViewSession'),
    url(r'^classes/(?P<session_slug>[\w\-_]+)/(?P<year>[0-9]+)/(?P<month>[\w]+)/(?P<slug>[\w\-_]+)/$', IndividualClassView.as_view(), name='classViewSessionMonth'),
    url(r'^events/(?P<session_slug>[\w\-_]+)/(?P<year>[0-9]+)/(?P<month>[\w]+)/(?P<slug>[\w\-_]+)/$', IndividualEventView.as_view(), name='eventViewSessionMonth'),

    url(r'^accounts/profile/(?P<user_id>[0-9]+)/$', OtherAccountProfileView.as_view(), name='accountProfile'),
    url(r'^accounts/profile/$', AccountProfileView.as_view(), name='accountProfile'),

]
