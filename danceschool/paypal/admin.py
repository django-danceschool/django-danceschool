from django.contrib import admin
from django.utils.html import format_html
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from .models import IPNMessage, IPNCartItem, Invoice


class IPNCartItemInline(admin.StackedInline):
    model = IPNCartItem
    extra = 0
    exclude = ['revenueItem',]

    def get_readonly_fields(self, request, obj=None):
        always_readonly = ['invoiceName','invoiceNumber','mc_gross','revenueItemLink']

        if request.user.has_perm('paypal.allocate_refunds') or request.user.is_superuser:
            return always_readonly
        else:
            return ['refundAmount'] + always_readonly

    def get_admin_change_link(self,app_label, model_name, obj_id, name):
        url = reverse('admin:%s_%s_change' % (app_label, model_name),
                      args=(obj_id,))
        return format_html('<a href="%s">%s</a>' % (
            url, str(name)
        ))

    def revenueItemLink(self,item):
        if item.initialCartItem.revenueItem:
            ri = item.initialCartItem.revenueItem
            return self.get_admin_change_link('financial','revenueitem',ri.id,ri.__str__())
        else:
            return None
    revenueItemLink.allow_tags = True
    revenueItemLink.short_description = _('Revenue Item')


class IPNMessageAdmin(admin.ModelAdmin):

    def get_admin_change_link(self,app_label, model_name, obj_id, name):
        url = reverse('admin:%s_%s_change' % (app_label, model_name),
                      args=(obj_id,))
        return format_html('<a href="%s">%s</a>' % (
            url, str(name)
        ))

    def finalRegistrationLink(self,item):
        if item.initialTransaction.finalRegistration:
            fr = item.initialTransaction.finalRegistration
            return self.get_admin_change_link('core','registration',fr.id,fr.__str__())
        else:
            return None
    finalRegistrationLink.allow_tags = True
    finalRegistrationLink.short_description = _('Final Registration')

    def registrationLink(self,item):
        if item.initialTransaction.registration:
            tr = item.initialTransaction.registration
            return self.get_admin_change_link('core','temporaryregistration',tr.id,tr.__str__())
        else:
            return None
    registrationLink.allow_tags = True
    registrationLink.short_description = _('Initial Temporary Registration')

    def priorTransactionLink(self,item):
        if item.priorTransaction:
            pt = item.priorTransaction
            return pt.payment_status + ': ' + self.get_admin_change_link('paypal','ipnmessage',pt.id,pt.txn_id) + '<br />'
        else:
            return None
    priorTransactionLink.allow_tags = True
    priorTransactionLink.short_description = _('Prior Transaction')

    def subsequentTransactionLinks(self,item):
        if item.subsequenttransactions.all():
            return '&nbsp;'.join([
                st.payment_status + ': ' + self.get_admin_change_link('paypal','ipnmessage',st.id,st.txn_id) + '<br />'
                for st in item.subsequenttransactions.all()
            ])
    subsequentTransactionLinks.allow_tags = True
    subsequentTransactionLinks.short_description = _('Subsequent Transactions')

    def existingInvoiceLink(self,item):
        if item.paypalInvoice:
            inv = item.paypalInvoice
            return self.get_admin_change_link('paypal','invoice',inv.id,item.generated_invoice)
        else:
            return item.generated_invoice
    existingInvoiceLink.allow_tags = True
    existingInvoiceLink.short_description = _('Paypal-Generated Invoice')

    inlines = [IPNCartItemInline,]

    list_display = ['id','registration','invoice','txn_id','payment_date','mc_gross','mc_fee','payment_status','payer_email']
    list_filter = ['payment_date','payment_status']
    search_fields = ['registration__firstName','registration__lastName','payer_email','txn_id','invoice']
    ordering = ['-payment_date',]
    readonly_fields = ['existingInvoiceLink','unallocatedRefunds','finalRegistrationLink','priorTransactionLink','subsequentTransactionLinks','registrationLink','netRevenue','invoice','payment_date','mc_gross','mc_fee','payment_status','txn_id','payer_id','payer_email','receiver_email','txn_type','mc_currency','custom']
    exclude = ['finalRegistration','registration','priorTransaction','generated_invoice']

    fieldsets = (
        (_('Overall Transaction Information'), {
            'fields': ('invoice','existingInvoiceLink','finalRegistrationLink','registrationLink','netRevenue','unallocatedRefunds'),
        }),
        (_('Related Transactions'), {
            'fields': ('priorTransactionLink','subsequentTransactionLinks',),
        }),
        (_('This IPN Message'), {
            'fields': ('txn_id','payment_date','mc_gross','mc_fee','payment_status','payer_id','payer_email','receiver_email','txn_type','mc_currency','custom'),
        }),
    )


class InvoiceAdmin(admin.ModelAdmin):
    def paypalLinks(self,item):
        return_string = ''

        if item.invoiceURL:
            return_string += '<a class="btn btn-default btn-xs" href="%s">%s</a>&nbsp;' % (item.invoiceURL, _('View Invoice'))
        if item.payerViewURL:
            return_string += '<a class="btn btn-default btn-xs" href="%s">%s</a>' % (item.payerViewURL, _('Pay Invoice'))
        return return_string

    paypalLinks.allow_tags = True
    paypalLinks.short_description = _('Links to Paypal Website')

    list_display = ['invoiceNumber','paypalInvoiceID','creationDate','paymentDate','totalAmount','paypalLinks']
    list_filter = ['creationDate','paymentDate']
    search_fields = ['invoiceNumber','paypalInvoiceID',]
    ordering = ['-creationDate',]
    readonly_fields = ['paypalLinks','itemList',]
    exclude = ['payerViewURL','invoiceURL']

    fieldsets = (
        ('Details', {
            'fields': ('invoiceNumber','paypalInvoiceID','totalAmount','paypalLinks','paymentDate','itemList'),
        }),
    )


admin.site.register(IPNMessage, IPNMessageAdmin)
admin.site.register(Invoice, InvoiceAdmin)
