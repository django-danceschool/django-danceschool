from django.urls import path

from .feeds import LatestNewsFeed
from .views import NewsView

urlpatterns = [
    # This shows the latest news, paginated
    path('', NewsView.as_view(), name='news'),

    # This is the latest news feed
    path('feed/', LatestNewsFeed(), name='news_feed'),
]
