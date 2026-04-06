from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from rangefilter.filters import DateRangeFilter

from ..models import EventRegistration, Registration


class EventRegistrationInline(admin.StackedInline):
    model = EventRegistration
    extra = 0
    fields = [
        'customer', 'event', 'role', 'cancelled', 'dropIn', 'occurrences',
        'item_grossTotal', 'item_total', 'partner_name'
    ]
    add_readonly_fields = ['item_grossTotal', 'item_total', 'partner_name']
    readonly_fields = ['customer', 'event', 'item_grossTotal', 'item_total', 'dropIn', 'occurrences', 'partner_name']
    autocomplete_fields = ['customer', ]

    def has_add_permission(self, request, obj=None):
        '''
        EventRegistrations can only be added to Registrations that are not final.
        '''
        if obj and obj.final:
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        '''
        EventRegistrations can only be deleted from Registrations that are not
        final.
        '''
        if obj and obj.final:
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        if not obj:
            return self.add_readonly_fields
        return self.readonly_fields

    def item_grossTotal(self, obj):
        return getattr(obj.invoiceItem, 'grossTotal', None)
    item_grossTotal.short_description = _('Total before discounts')

    def item_total(self, obj):
        return getattr(obj.invoiceItem, 'total', None)
    item_total.short_description = _('Total billed amount')

    def partner_name(self, obj):
        if obj.event.partnerRequired and obj.data.get('partner', {}):
            name = ' '.join([
                obj.data['partner'].get('firstName',''),
                obj.data['partner'].get('lastName',''),
            ])
            customerId = obj.data['partner'].get('customerId')

            if customerId:
                change_url = reverse('admin:core_customer_change', args=(customerId, ))
                return mark_safe(
                    '<a href="%s">%s</a>' % (change_url, name or _('N/A'))
                )
            return name or _('N/A')
        return _('N/A')

    partner_name.short_description = _('Partner')


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    inlines = [EventRegistrationInline]
    list_display = ['invoice_name', 'final', 'dateTime', 'total',]
    list_filter = ['final', ('dateTime', DateRangeFilter), 'invoice__paidOnline']
    search_fields = [
        'invoice__firstName', 'invoice__lastName', 'invoice__email',
    ]
    ordering = ('-final', '-dateTime', )
    fields = (
        ('final', 'invoice_expiry'), 'invoice_name', 'invoice_link',
        'total', 'dateTime', 'comments',
        'howHeardAboutUs', 'submissionUser',
    )
    readonly_fields = ('total', 'invoice_name', 'invoice_link', 'invoice_expiry')

    def invoice_name(self, obj):
        name = getattr(obj.invoice, 'fullName', _('N/A'))
        if getattr(obj.invoice, 'email', None):
            name += ': %s' % obj.invoice.email
        return name
    invoice_name.short_description = _('Registrant Name')

    def invoice_link(self, obj):
        change_url = reverse('admin:core_invoice_change', args=(obj.invoice.id, ))
        return mark_safe('<a href="%s">%s</a>' % (change_url, obj.invoice))
    invoice_link.allow_tags = True
    invoice_link.short_description = _("Invoice")

    def invoice_expiry(self, obj):
        return obj.invoice.expirationDate
    invoice_expiry.short_description = _("Expiration Date")
