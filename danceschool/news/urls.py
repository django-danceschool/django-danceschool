from django.conf.urls import re_path

from .feeds import LatestNewsFeed
from .views import NewsView

urlpatterns = [
 	# This shows the latest news, paginated
 	re_path(r'^',NewsView.as_view(), name='news'),

    # This is the latest news feed
    re_path(r'^feed/',LatestNewsFeed(), name='news_feed'),
]
