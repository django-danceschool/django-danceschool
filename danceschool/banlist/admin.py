from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

from .models import BannedPerson, BannedEmail, BanFlaggedRecord


class BannedEmailInline(admin.StackedInline):
    model = BannedEmail
    extra = 1
    exclude = []


@admin.register(BannedPerson)
class BannedPersonAdmin(admin.ModelAdmin):
    list_display = ('fullName', 'photoThumbnail', 'enabled', 'expirationDate', )
    list_filter = ('disabled', 'expirationDate', )
    search_fields = ('=firstName', '=lastName', 'bannedemail__email', 'banflaggedrecord__flagCode', )
    readonly_fields = ('submissionDate', 'modifiedDate')

    inlines = [BannedEmailInline, ]

    actions = ('enableBan', 'disableBan', )

    def enabled(self, obj):
        return obj.disabled is False
    enabled.short_description = _('Enabled')
    enabled.boolean = True

    def photoThumbnail(self, obj):
        if obj.photo:
            return u'<img src="%s" />' % (obj.photo.icons.get('64'))
        return ''
    photoThumbnail.short_description = _('Thumbnail')
    photoThumbnail.allow_tags = True

    def enableBan(self, request, queryset):
        rows_updated = queryset.update(disabled=False)
        if rows_updated == 1:
            message_bit = "1 ban was"
        else:
            message_bit = "%s bans were" % rows_updated
        self.message_user(request, "%s enabled." % message_bit)
    enableBan.short_description = _('Enable selected bans')

    def disableBan(self, request, queryset):
        rows_updated = queryset.update(disabled=True)
        if rows_updated == 1:
            message_bit = "1 ban was"
        else:
            message_bit = "%s bans were" % rows_updated
        self.message_user(request, "%s disabled." % message_bit)
    disableBan.short_description = _('Disable selected bans')


@admin.register(BanFlaggedRecord)
class BanFlaggedRecordAdmin(admin.ModelAdmin):
    list_display = ('_personFullName', 'dateTime', 'ipAddress', 'flagCode', )
    list_filter = ('dateTime', )
    search_fields = ('=person__firstName', '=person__lastName', 'person__bannedemail__email', 'flagCode', )
    readonly_fields = ('person', 'dateTime', 'ipAddress', 'flagCode', 'data', )

    def _personFullName(self, obj):
        return obj.person.fullName
    _personFullName.short_description = _('Person')
