from django.urls import path

from danceschool.core.classreg import ClassRegistrationView
from .views import RegisterView
from .autocomplete_light_registry import RegisterAutoComplete

urlpatterns = [
    # This is kept to avoid breaking the path to the prior traditional registration URL.
    path('', ClassRegistrationView.as_view(), name='registration'),

    path('autocomplete/', RegisterAutoComplete.as_view(), name='registerAutocomplete'),
    path('<slug:slug>/<int:year>/<int:month>/<int:day>/', RegisterView.as_view(), name='registerView'),
    path('<slug:slug>/', RegisterView.as_view(today=True), name='registerView'),
]
