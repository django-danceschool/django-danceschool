from cms.app_base import CMSApp
from cms.apphook_pool import apphook_pool
from django.utils.translation import ugettext_lazy as _


class RegistrationApphook(CMSApp):
    name = _("Registration Apphook")

    def get_urls(self, page=None, language=None, **kwargs):
        return ["danceschool.core.urls_registration"]


apphook_pool.register(RegistrationApphook)
