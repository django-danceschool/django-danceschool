from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from rangefilter.filters import DateRangeFilter

from .models import SquarePaymentRecord


class SquarePaymentRecordAdmin(admin.ModelAdmin):

    def get_admin_change_link(self, app_label, model_name, obj_id, name):
        url = reverse('admin:%s_%s_change' % (app_label, model_name),
                      args=(obj_id, ))
        return format_html('<a href="%s">%s</a>' % (
            url, str(name)
        ))

    def invoiceLink(self, item):
        if item.invoice:
            i = item.invoice
            return self.get_admin_change_link('core', 'invoice', i.id, i.id)
    invoiceLink.allow_tags = True
    invoiceLink.short_description = _('Registration invoice')

    def receiptLink(self, item):
        return mark_safe(
            f'<a href="{item.receiptUrl}" target="_blank">{item.receiptNumber}</a>'
        )
    receiptLink.allow_tags = True
    receiptLink.short_description = _('Square Receipt')

    list_display = [
        'paymentId', 'apiPaymentCreated', 'apiPaymentModified',
        'netAmountPaid', 'netFees', 'invoiceLink', 'receiptLink'
    ]
    list_filter = [
        ('creationDate', DateRangeFilter),
        ('apiPaymentCreated', DateRangeFilter),
        ('apiPaymentModified', DateRangeFilter),
        'locationId'
    ]
    search_fields = ['paymentId', 'orderId', 'invoice__id']

    ordering = ['-modifiedDate', '-creationDate']
    readonly_fields = [
        'paymentId', 'orderId', 'locationId',
        'creationDate', 'modifiedDate',
        'netAmountPaid', 'netFees',
        'invoiceLink', 'receiptLink',
        'apiPaymentCreated', 'apiPaymentModified'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'paymentId', 'orderId',
                'netAmountPaid', 'netFees',
                'invoiceLink', 'receiptLink'
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


admin.site.register(SquarePaymentRecord, SquarePaymentRecordAdmin)
