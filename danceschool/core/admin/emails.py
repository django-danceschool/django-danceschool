from django.contrib import admin
from django.forms import ModelForm, RadioSelect
from django.utils.translation import gettext_lazy as _

from ..models import EmailTemplate


class EmailTemplateAdminForm(ModelForm):

    class Meta:
        model = EmailTemplate
        exclude = []

        widgets = {
            'richTextChoice': RadioSelect,
        }

    class Media:
        js = ('js/emailtemplate_contenttype.js', )


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    form = EmailTemplateAdminForm

    list_display = ('name', 'richTextChoice', 'hideFromForm')
    list_filter = ('richTextChoice', 'groupRequired', 'hideFromForm')
    ordering = ('name', )

    fieldsets = (
        (None, {
            'fields': ('name', 'richTextChoice', 'subject', ),
        }),
        (_('Plain text content'), {
            'fields': ('content', ),
        }),
        (_('Rich text HTML content'), {
            'fields': ('html_content', ),
        }),
        (None, {
            'fields': (
                'defaultFromName', 'defaultFromAddress', 'defaultCC',
                'groupRequired', 'hideFromForm'
            ),
        }),
    )
