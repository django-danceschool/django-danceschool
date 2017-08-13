from django.conf.urls import url

from .ajax import CustomerRequirementAjaxView

urlpatterns = [
    url(r'^customer/$', CustomerRequirementAjaxView.as_view(), name='customerRequirementAjax'),
]
