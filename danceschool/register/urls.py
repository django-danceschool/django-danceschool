from django.urls import path

from .views import PointOfSaleRegisterView
from .autocomplete_light_registry import RegisterAutoComplete

urlpatterns = [
    path('autocomplete/', RegisterAutoComplete.as_view(), name='registerAutocomplete'),
    path('<slug:slug>/<int:year>/<int:month>/<int:day>/', PointOfSaleRegisterView.as_view(), name='registerView'),
    path('<slug:slug>/', PointOfSaleRegisterView.as_view(today=True), name='registerView'),
]
