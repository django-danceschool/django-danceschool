from django.urls import path, include
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
    path(
        'settings/global/',
        user_passes_test(lambda u: u.is_superuser)(PreferenceFormView.as_view(
            registry=global_preferences_registry,
            form_class=GlobalPreferenceForm,
            template_name='dynamic_preferences/form_danceschool.html',)),
        name="dynamic_preferences.global"
    ),

    path(
        'settings/global/<str:section>/',
        user_passes_test(lambda u: u.is_superuser)(PreferenceFormView.as_view(
            registry=global_preferences_registry,
            form_class=GlobalPreferenceForm,
            template_name='dynamic_preferences/form_danceschool.html',)),
        name="dynamic_preferences.global.section"
    ),

    # For Django-filer
    path('filer/', include('filer.urls')),
    path('', include('filer.server.urls')),

    # For Django-filer in CKeditor
    path('filebrowser_filer/', include('ckeditor_filebrowser_filer.urls')),

    # For automatically-generated sitemaps
    path(
        'sitemap.xml', sitemap,
        {'sitemaps': {'event': EventSitemap, 'page': CMSSitemap}},
        name='django.contrib.sitemaps.views.sitemap'
    ),

    # For better authentication
    path('accounts/', include('allauth.urls')),

    # The URLS associated with all built-in core functionality.
    path('', include('danceschool.core.urls')),
    path('registration/', include('danceschool.core.urls_registration')),
]

# If additional danceschool apps are installed, automatically add those URLs as well.
if apps.is_installed('danceschool.banlist'):
    urlpatterns.append(path('banlist/', include('danceschool.banlist.urls')),)

if apps.is_installed('danceschool.discounts'):
    urlpatterns.append(path('discounts/', include('danceschool.discounts.urls')),)

if apps.is_installed('danceschool.financial'):
    urlpatterns.append(path('financial/', include('danceschool.financial.urls')),)

if apps.is_installed('danceschool.guestlist'):
    urlpatterns.append(path('guest-list/', include('danceschool.guestlist.urls')),)

if apps.is_installed('danceschool.register'):
    urlpatterns.append(path('register/', include('danceschool.register.urls')),)

if apps.is_installed('danceschool.prerequisites'):
    urlpatterns.append(path('prerequisites/', include('danceschool.prerequisites.urls')),)

if apps.is_installed('danceschool.private_events'):
    urlpatterns.append(path('private-events/', include('danceschool.private_events.urls')),)

if apps.is_installed('danceschool.private_lessons'):
    urlpatterns.append(path('private-lessons/', include('danceschool.private_lessons.urls')),)

if apps.is_installed('danceschool.vouchers'):
    urlpatterns.append(path('vouchers/', include('danceschool.vouchers.urls')),)

if apps.is_installed('danceschool.payments.payatdoor'):
    urlpatterns.append(path('payatdoor/', include('danceschool.payments.payatdoor.urls')),)

if apps.is_installed('danceschool.payments.paypal'):
    urlpatterns.append(path('paypal/', include('danceschool.payments.paypal.urls')),)

if apps.is_installed('danceschool.payments.stripe'):
    urlpatterns.append(path('stripe/', include('danceschool.payments.stripe.urls')),)

if apps.is_installed('danceschool.payments.square'):
    urlpatterns.append(path('square/', include('danceschool.payments.square.urls')),)
