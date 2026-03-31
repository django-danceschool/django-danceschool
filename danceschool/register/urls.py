from django.urls import path

from danceschool.core.classreg import ClassRegistrationView
from .views import PointOfSaleRegisterView, PublicRegisterView
from .autocomplete_light_registry import RegisterAutoComplete

urlpatterns = [
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

    path('autocomplete/', RegisterAutoComplete.as_view(), name='registerAutocomplete'),
    path('<slug:slug>/<int:year>/<int:month>/<int:day>/', PointOfSaleRegisterView.as_view(), name='registerView'),
    path('<slug:slug>/', PointOfSaleRegisterView.as_view(today=True), name='registerView'),
]
