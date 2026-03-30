from django.urls import path

from danceschool.core.classreg import ClassRegistrationView
from .views import PointOfSaleRegisterView, PublicRegisterView
from .autocomplete_light_registry import RegisterAutoComplete

urlpatterns = [
    # This is kept to avoid breaking the path to the prior traditional registration URL.
    path('', ClassRegistrationView.as_view(), name='registration'),

    # New plugin-based public registration page.  Will replace the path above
    # once ClassRegistrationView is retired.
    path('public/', PublicRegisterView.as_view(), name='publicRegistration'),
    path(
        'public/referral/<slug:voucher_id>/',
        PublicRegisterView.as_view(),
        name='publicRegistrationWithVoucher',
    ),
    path(
        'public/id/<slug:marketing_id>/',
        PublicRegisterView.as_view(),
        name='publicRegistrationWithMarketingId',
    ),

    path('autocomplete/', RegisterAutoComplete.as_view(), name='registerAutocomplete'),
    path('<slug:slug>/<int:year>/<int:month>/<int:day>/', PointOfSaleRegisterView.as_view(), name='registerView'),
    path('<slug:slug>/', PointOfSaleRegisterView.as_view(today=True), name='registerView'),
]
