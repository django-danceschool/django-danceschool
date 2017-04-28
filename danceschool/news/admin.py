from django.contrib import admin

from .models import NewsItem


class NewsItemAdmin(admin.ModelAdmin):
    list_display = ('title','alert','pinThis','publicationDate','modifiedDate')
    list_display_links = ('title',)
    list_filter = ('publicationDate','modifiedDate','alert','pinThis')


admin.site.register(NewsItem, NewsItemAdmin)
