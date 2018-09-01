from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

from adminsortable2.admin import SortableAdminMixin
from cms.admin.placeholderadmin import FrontendEditableAdminMixin

from .models import FAQCategory, FAQ


class FAQCategoryAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ('name',)


class FAQAdmin(SortableAdminMixin, FrontendEditableAdminMixin, admin.ModelAdmin):
    list_display = ('question','category','draft')
    list_filter = ('category','draft')
    list_editable = ('category',)
    actions = ('publishFaq','makeDraft',)

    def publishFaq(self, request, queryset):
        rows_updated = queryset.update(draft=False)
        if rows_updated == 1:
            message_bit = "1 FAQ was"
        else:
            message_bit = "%s FAQs were" % rows_updated
        self.message_user(request, "%s successfully published." % message_bit)
    publishFaq.short_description = _('Publish selected FAQs')

    def makeDraft(self, request, queryset):
        rows_updated = queryset.update(draft=True)
        if rows_updated == 1:
            message_bit = "1 FAQ was"
        else:
            message_bit = "%s FAQs were" % rows_updated
        self.message_user(request, "%s successfully unpublished (made draft)." % message_bit)
    makeDraft.short_description = _('Unpublish selected FAQs')


admin.site.register(FAQCategory, FAQCategoryAdmin)
admin.site.register(FAQ, FAQAdmin)
