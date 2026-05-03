from cms.app_base import CMSAppConfig
from django.utils import timezone

from danceschool.core.utils.timezone import ensure_localtime

from .models import Register
from .views import PointOfSaleRegisterView


def render_register(request, register):
    today = ensure_localtime(timezone.now())
    return PointOfSaleRegisterView.as_view()(
        request,
        slug=register.slug,
        year=today.year,
        month=today.month,
        day=today.day,
    )


class RegisterCMSConfig(CMSAppConfig):
    cms_enabled = True
    cms_toolbar_enabled_models = [(Register, render_register)]
