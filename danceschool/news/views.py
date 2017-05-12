from django.views.generic import ListView

from .models import NewsItem


class NewsView(ListView):
    queryset = NewsItem.objects.all()
    paginate_by = 5
    template_name = 'news/news_listing.html'
