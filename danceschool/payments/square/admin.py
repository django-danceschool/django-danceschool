from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from rangefilter.filters import DateRangeFilter

from danceschool.core.constants import getConstant
from .models import SquarePaymentRecord, SquarePayoutRecord, SquarePayoutEntry


class SquarePaymentRecordAdmin(admin.ModelAdmin):

    def get_admin_change_link(self, app_label, model_name, obj_id, name):
        url = reverse('admin:%s_%s_change' % (app_label, model_name),
                      args=(obj_id, ))
        return mark_safe(f'<a href="{url}">{name}</a>')

    def invoiceLink(self, item):
        change_url = reverse('viewOrCreatePaymentInvoice', args=(item.pk, ))
        link_text = getattr(item.invoice, 'id', _('Create an invoice'))
        return mark_safe(f'<a href="{change_url}">{link_text}</a>')
    invoiceLink.allow_tags = True
    invoiceLink.short_description = _('Invoice')

    def receiptLink(self, item):
        return mark_safe(
            f'<a href="{item.receiptUrl}" target="_blank">{item.receiptNumber}</a>'
        )
    receiptLink.allow_tags = True
    receiptLink.short_description = _('Square Receipt')

    def payoutLinks(self, item, includeAmount=True):
        entries = item.getPayoutEntries()
        links = []
        for entry in entries:
            entry_label = (
                f'{entry.payoutDate.strftime("%Y-%m-%d")}: {getConstant('general__currencySymbol')}{entry.amountPaid}'
                if includeAmount else
                f'{entry.payoutDate.strftime("%Y-%m-%d")}'
            )
            links += [
                self.get_admin_change_link(
                    'square', 'squarepayoutrecord', entry.payout.payoutId,
                    entry_label
                ),
                mark_safe('<br />')
            ]
        return format_html(''.join(links))
    payoutLinks.allow_tags = True
    payoutLinks.short_description = _('Square payouts')

    def payoutLinksShort(self, item):
        return self.payoutLinks(item, includeAmount=False)
    payoutLinksShort.allow_tags = True
    payoutLinksShort.short_description = _('Square payouts')

    list_display = (
        'paymentId', 'apiPaymentCreated', 'apiPaymentModified',
        'netAmountPaid', 'netFees', 'payoutLinksShort', 'invoiceLink', 'receiptLink'
    )
    list_filter = (
        ('creationDate', DateRangeFilter),
        ('modifiedDate', DateRangeFilter),
        'locationId',
        ('invoice', admin.EmptyFieldListFilter),
    )
    search_fields = ('paymentId', 'orderId', 'invoice__id')

    ordering = ('-modifiedDate', '-creationDate')
    readonly_fields = (
        'paymentId', 'orderId', 'locationId',
        'creationDate', 'modifiedDate',
        'netAmountPaid', 'netFees',
        'invoiceLink', 'receiptLink', 'payoutLinks',
        'apiPaymentCreated', 'apiPaymentModified'
    )

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'paymentId', 'orderId',
                'netAmountPaid', 'netFees',
                'invoiceLink', 'payoutLinks', 'receiptLink'
            ),
        }),
        (_('Dates'), {
            'fields': (
                'apiPaymentCreated', 'apiPaymentModified',
                'creationDate', 'modifiedDate'
            ),
        }),
        (_('Additional Data'), {
            'classes': ('collapse', ),
            'fields': ('data',),
        }),
    )


class SquarePayoutEntryInline(admin.TabularInline):

    def get_admin_change_link(self, app_label, model_name, obj_id, name):
        url = reverse('admin:%s_%s_change' % (app_label, model_name),
                      args=(obj_id, ))
        return mark_safe(f'<a href="{url}">{name}</a>')

    def paymentRecordLink(self, item):
        return self.get_admin_change_link(
            'square', 'squarepaymentrecord',
            item.paymentRecord.id, item.paymentRecord.paymentId
        )
    paymentRecordLink.allow_tags = True
    paymentRecordLink.short_description = _('Payment record')

    model = SquarePayoutEntry
    extra = 0
    fields = ('entryId', 'amountPaid', 'paymentRecordLink')
    readonly_fields = ('entryId', 'amountPaid', 'paymentRecordLink')

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SquarePayoutRecordAdmin(admin.ModelAdmin):

    list_display = (
        'payoutId', 'payoutDate',
        'amountPaid'
    )
    list_filter = (
        ('creationDate', DateRangeFilter),
        ('modifiedDate', DateRangeFilter),
        'locationId',
    )
    search_fields = ('payoutId',)

    ordering = ('-modifiedDate', '-creationDate')
    readonly_fields = (
        'payoutId', 'locationId', 'amountPaid',
        'creationDate', 'modifiedDate', 'payoutDate'
    )

    inlines = (SquarePayoutEntryInline,)

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'payoutId', 'locationId', 'amountPaid',
                'creationDate', 'modifiedDate', 'payoutDate',
            ),
        }),
        (_('Additional Data'), {
            'classes': ('collapse', ),
            'fields': ('data',),
        }),
    )


admin.site.register(SquarePaymentRecord, SquarePaymentRecordAdmin)
admin.site.register(SquarePayoutRecord, SquarePayoutRecordAdmin)
