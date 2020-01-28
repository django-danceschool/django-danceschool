from django.urls import path

from .ajax import CustomerRequirementAjaxView

urlpatterns = [
    path('customer/', CustomerRequirementAjaxView.as_view(), name='customerRequirementAjax'),
]
