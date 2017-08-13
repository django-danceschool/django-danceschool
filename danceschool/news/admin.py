from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

from .models import NewsItem


class NewsItemAdmin(admin.ModelAdmin):
    list_display = ('title','alert','pinThis','publicationDate','modifiedDate')
    list_display_links = ('title',)
    list_filter = ('publicationDate','modifiedDate','alert','pinThis')
    readonly_fields = ('modifiedDate',)

    fieldsets = (
        (None, {
            'fields': ('title','content',('alert','pinThis'),('draft','hideThis'),)
        }),
        (_('Dates'),{
            'classes': ('collapse',),
            'fields': ('publicationDate','modifiedDate'),
        }),
    )


admin.site.register(NewsItem, NewsItemAdmin)
