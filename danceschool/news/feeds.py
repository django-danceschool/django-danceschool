from django.contrib.syndication.views import Feed
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from .models import NewsItem

from danceschool.core.constants import getConstant


class LatestNewsFeed(Feed):

    def title(self):
        return _("%s Latest News" % getConstant('contact__businessName'))

    def description(self):
        return _("Updates and news items from %s" % getConstant('contact__businessName'))

    def link(self):
        return reverse('news_feed')

    def items(self):
        return NewsItem.objects.order_by('-publicationDate')[:10]

    def item_title(self, item):
        return item.title

    def item_pubDate(self, item):
        return item.publicationDate

    def item_description(self, item):
        return item.content

    # item_link is only needed if NewsItem has no get_absolute_url method.
    def item_link(self, item):
        return reverse('news_feed')
