from cms.app_base import CMSApp
from cms.apphook_pool import apphook_pool
from django.utils.translation import gettext_lazy as _


class NewsApphook(CMSApp):
    name = _("News Apphook")

    def get_urls(self, page=None, language=None, **kwargs):
        return ["danceschool.news.urls"]


apphook_pool.register(NewsApphook)
