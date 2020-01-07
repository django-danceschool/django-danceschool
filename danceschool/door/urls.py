from django.urls import path

from .views import DoorRegisterView
from .autocomplete_light_registry import DoorRegisterAutoComplete

urlpatterns = [
    path('register/<slug:slug>/<int:year>/<int:month>/<int:day>/', DoorRegisterView.as_view(), name='doorRegister'),
    path('register/autocomplete/', DoorRegisterAutoComplete.as_view(), name='doorRegisterAutocomplete'),
]
