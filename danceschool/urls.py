from django.conf.urls import include, url
from django.contrib.auth.decorators import user_passes_test
from django.contrib.sitemaps.views import sitemap

from cms.sitemaps import CMSSitemap

from dynamic_preferences.views import PreferenceFormView
from dynamic_preferences.registries import global_preferences_registry
from dynamic_preferences.forms import GlobalPreferenceForm

from danceschool.core.sitemaps import EventSitemap

urlpatterns = [
    # For site configuration
    url(r'^settings/global/$',
        user_passes_test(lambda u: u.is_superuser)(PreferenceFormView.as_view(
            registry=global_preferences_registry,
            form_class=GlobalPreferenceForm)),
        name="dynamic_preferences.global"),
    url(r'^settings/global/(?P<section>[\w\ ]+)$',
        user_passes_test(lambda u: u.is_superuser)(PreferenceFormView.as_view(
            registry=global_preferences_registry,
            form_class=GlobalPreferenceForm)),
        name="dynamic_preferences.global.section"),
    # For Django-filer
    url(r'^filer/', include('filer.urls')),
    url(r'^', include('filer.server.urls')),
    # For Django-filer in CKeditor
    url(r'^filebrowser_filer/', include('ckeditor_filebrowser_filer.urls')),
    # For automatically-generated sitemaps
    url(r'^sitemap\.xml$', sitemap, {'sitemaps': {'event': EventSitemap, 'page': CMSSitemap}},name='django.contrib.sitemaps.views.sitemap'),
    # For better authentication
    url(r'^accounts/', include('allauth.urls')),

    # The URLS associated with all built-in functionality. Notice that the CMS URLs go last,
    # because they will match any pattern that has not already been matched.
    url(r'^', include('danceschool.core.urls')),
    url(r'^register/', include('danceschool.core.urls_registration')),
    url(r'^paypal/', include('danceschool.paypal.urls')),
    url(r'^financial/', include('danceschool.financial.urls')),
    url(r'^private_events/', include('danceschool.private_events.urls')),
    url(r'^', include('cms.urls')),
]
