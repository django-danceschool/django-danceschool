from django.urls import path

from .views import PointOfSaleRegisterView
from .autocomplete_light_registry import RegisterAutoComplete
from danceschool.core.views.registration import PublicRegisterView

urlpatterns = [
    path('', PublicRegisterView.as_view(), name='registration'),
    path('autocomplete/', RegisterAutoComplete.as_view(), name='registerAutocomplete'),
    path('<slug:slug>/<int:year>/<int:month>/<int:day>/', PointOfSaleRegisterView.as_view(), name='registerView'),
    path('<slug:slug>/', PointOfSaleRegisterView.as_view(today=True), name='registerView'),
]
