from django.contrib.sitemaps import Sitemap

from .models import Event


class EventSitemap(Sitemap):
    changefreq = "monthly"
    protocol = "https"

    def items(self):
        return Event.objects.exclude(status=Event.RegStatus.hidden)

    def lastmod(self, obj):
        return obj.modified
