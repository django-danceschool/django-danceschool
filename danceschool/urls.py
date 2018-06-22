from django.conf.urls import include, url
from django.contrib.auth.decorators import user_passes_test
from django.contrib.sitemaps.views import sitemap
from django.apps import apps

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
            form_class=GlobalPreferenceForm,
            template_name='dynamic_preferences/form_danceschool.html',)),
        name="dynamic_preferences.global"),

    url(r'^settings/global/(?P<section>[\w\ ]+)$',
        user_passes_test(lambda u: u.is_superuser)(PreferenceFormView.as_view(
            registry=global_preferences_registry,
            form_class=GlobalPreferenceForm,
            template_name='dynamic_preferences/form_danceschool.html',)),
        name="dynamic_preferences.global.section"),

    # For Django-filer
    url(r'^filer/', include('filer.urls')),
    url(r'^', include('filer.server.urls')),

    # For Django-filer in CKeditor
    url(r'^filebrowser_filer/', include('ckeditor_filebrowser_filer.urls')),

    # For automatically-generated sitemaps
    url(r'^sitemap\.xml$',
        sitemap,
        {'sitemaps': {'event': EventSitemap, 'page': CMSSitemap}},
        name='django.contrib.sitemaps.views.sitemap'),

    # For better authentication
    url(r'^accounts/', include('allauth.urls')),

    # For Django CMS forms
    url(r'^', include('djangocms_forms.urls')),
    
    # The URLS associated with all built-in core functionality.
    url(r'^', include('danceschool.core.urls')),
    url(r'^register/', include('danceschool.core.urls_registration')),
]

# If additional danceschool apps are installed, automatically add those URLs as well.
if apps.is_installed('danceschool.banlist'):
    urlpatterns.append(url(r'^banlist/', include('danceschool.banlist.urls')),)

if apps.is_installed('danceschool.discounts'):
    urlpatterns.append(url(r'^discounts/', include('danceschool.discounts.urls')),)

if apps.is_installed('danceschool.financial'):
    urlpatterns.append(url(r'^financial/', include('danceschool.financial.urls')),)

if apps.is_installed('danceschool.prerequisites'):
    urlpatterns.append(url(r'^prerequisites/', include('danceschool.prerequisites.urls')),)

if apps.is_installed('danceschool.private_events'):
    urlpatterns.append(url(r'^private-events/', include('danceschool.private_events.urls')),)

if apps.is_installed('danceschool.private_lessons'):
    urlpatterns.append(url(r'^private-lessons/', include('danceschool.private_lessons.urls')),)

if apps.is_installed('danceschool.vouchers'):
    urlpatterns.append(url(r'^vouchers/', include('danceschool.vouchers.urls')),)

if apps.is_installed('danceschool.payments.paypal'):
    urlpatterns.append(url(r'^paypal/', include('danceschool.payments.paypal.urls')),)

if apps.is_installed('danceschool.payments.stripe'):
    urlpatterns.append(url(r'^stripe/', include('danceschool.payments.stripe.urls')),)

if apps.is_installed('danceschool.payments.square'):
    urlpatterns.append(url(r'^square/', include('danceschool.payments.square.urls')),)
