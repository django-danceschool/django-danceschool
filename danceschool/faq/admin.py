from django.contrib import admin
from adminsortable2.admin import SortableAdminMixin
from cms.admin.placeholderadmin import FrontendEditableAdminMixin

from .models import FAQCategory, FAQ


class FAQCategoryAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ('name',)


class FAQAdmin(SortableAdminMixin, FrontendEditableAdminMixin, admin.ModelAdmin):
    list_display = ('question','category','draft')
    list_filter = ('category','draft')
    lsit_editable = ('category','draft')


admin.site.register(FAQCategory, FAQCategoryAdmin)
admin.site.register(FAQ, FAQAdmin)
