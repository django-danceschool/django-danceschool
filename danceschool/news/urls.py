from django.conf.urls import url

from .feeds import LatestNewsFeed
from .views import NewsView

urlpatterns = [
 	# This shows the latest news, paginated
 	url(r'^$',NewsView.as_view(), name='news'),

    # This is the latest news feed
    url(r'^feed/$',LatestNewsFeed(), name='news_feed'),
]
