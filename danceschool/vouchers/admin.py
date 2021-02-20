from django.contrib import admin
from django.forms import ModelForm, ModelChoiceField, TextInput
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.safestring import mark_safe

from dal import autocomplete

from danceschool.core.models import Customer, Invoice
from danceschool.core.admin import CustomerAdmin

from .models import (
    VoucherCategory, Voucher, DanceTypeVoucher, ClassVoucher,
    SeriesCategoryVoucher, PublicEventCategoryVoucher, SessionVoucher,
    CustomerGroupVoucher, CustomerVoucher, VoucherUse,
    VoucherCredit
)


class CustomerVoucherInlineForm(ModelForm):
    customer = ModelChoiceField(
        queryset=Customer.objects.all(),
        widget=autocomplete.ModelSelect2(
            url='autocompleteCustomer',
            attrs={
                # This will set the input placeholder attribute:
                'data-placeholder': _('Enter a customer name'),
                # This will set the yourlabs.Autocomplete.minimumCharacters
                # options, the naming conversion is handled by jQuery
                'data-minimum-input-length': 2,
                'data-max-results': 4,
                'class': 'modern-style',
            }
        )
    )

    class Meta:
        model = CustomerVoucher
        exclude = []

    class Media:
        js = (
            'admin/js/vendor/jquery/jquery.min.js',
            'admin/js/jquery.init.js',
        )


class CustomerGroupVoucherInline(admin.StackedInline):
    model = CustomerGroupVoucher
    extra = 1
    classes = ['collapse', ]


class CustomerVoucherInline(admin.StackedInline):
    model = CustomerVoucher
    form = CustomerVoucherInlineForm
    extra = 1
    classes = ['collapse', ]


class CustomerAdminWithVouchers(CustomerAdmin):
    inlines = CustomerAdmin.inlines + [CustomerVoucherInline]


class InvoiceVoucherInline(admin.TabularInline):
    model = VoucherUse
    extra = 0
    readonly_fields = ['voucher', 'amount']
    exclude = ['applied', 'beforeTax']

    # Prevents adding new voucher uses without going through
    # the standard registration process
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class DanceTypeVoucherInline(admin.StackedInline):
    model = DanceTypeVoucher
    extra = 1
    classes = ['collapse', ]


class ClassVoucherInline(admin.StackedInline):
    model = ClassVoucher
    extra = 1
    classes = ['collapse', ]


class SeriesCategoryVoucherInline(admin.StackedInline):
    model = SeriesCategoryVoucher
    extra = 1
    classes = ['collapse', ]


class PublicEventCategoryVoucherInline(admin.StackedInline):
    model = PublicEventCategoryVoucher
    extra = 1
    classes = ['collapse', ]


class EventSessionVoucherInline(admin.StackedInline):
    model = SessionVoucher
    extra = 1
    classes = ['collapse', ]


class ClassVoucherInline(admin.StackedInline):
    model = ClassVoucher
    extra = 1
    classes = ['collapse', ]


class VoucherUseInline(admin.TabularInline):
    model = VoucherUse
    extra = 0
    fields = ('viewInvoiceLink', 'creationDate', 'amount', 'notes')
    readonly_fields = ('viewInvoiceLink', 'creationDate', 'amount')

    def viewInvoiceLink(self, obj):
        if obj.id:
            change_url = reverse('viewInvoice', args=(obj.invoice.id, ))
            return mark_safe(
                '<a class="btn btn-outline-secondary" href="%s">%s</a>' % (change_url, obj.invoice.id)
            )
    viewInvoiceLink.allow_tags = True
    viewInvoiceLink.short_description = _('Invoice')

    # Prevents adding new voucher uses without going through
    # the standard registration process.
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        '''
        Inline only shows voucher uses associated with finalized registrations.
        '''
        qs = super().get_queryset(request)
        return qs.filter(applied=True)


class VoucherCreditInlineForm(ModelForm):

    class Meta:
        widgets = {
            'description': TextInput,
        }


class VoucherCreditInline(admin.TabularInline):
    model = VoucherCredit
    extra = 1
    fields = ['amount', 'description', 'creationDate']
    readonly_fields = ['creationDate', ]

    form = VoucherCreditInlineForm


class VoucherAdmin(admin.ModelAdmin):
    inlines = [
        DanceTypeVoucherInline, ClassVoucherInline, SeriesCategoryVoucherInline,
        PublicEventCategoryVoucherInline, EventSessionVoucherInline,
        CustomerGroupVoucherInline, CustomerVoucherInline, VoucherUseInline,
        VoucherCreditInline
    ]
    list_display = [
        'voucherId', 'name', 'category', 'amountLeft', 'maxAmountPerUse',
        'isEnabled', 'restrictions'
    ]
    list_filter = [
        'category', 'expirationDate', 'disabled', 'forFirstTimeCustomersOnly',
        'forPreviousCustomersOnly', 'doorOnly', 'beforeTax',
    ]
    search_fields = ['voucherId', 'name', 'description']
    add_readonly_fields = ['refundAmount', 'creationDate', 'amountLeft']
    readonly_fields = ['originalAmount', 'refundAmount', 'creationDate', 'amountLeft']
    actions = ['enableVoucher', 'disableVoucher']

    fieldsets = (
        (None, {
            'fields': (('voucherId', 'category'), 'name', 'description', ('originalAmount', 'amountLeft'), ('maxAmountPerUse', 'beforeTax')),
        }),
        (_('Voucher Restrictions'), {
            'fields': (
                'expirationDate', (
                    'singleUse', 'forFirstTimeCustomersOnly',
                    'forPreviousCustomersOnly', 'doorOnly', 'disabled'
                )
            ),
        }),
        (_('Other Info'), {
            'classes': ('collapse', ),
            'fields': ('creationDate', 'refundAmount'),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        if not obj:
            return self.add_readonly_fields
        return self.readonly_fields

    def isEnabled(self, obj):
        return obj.disabled is False
    isEnabled.short_description = _('Enabled')
    isEnabled.boolean = True

    def restrictions(self, obj):
        text = []
        if not obj.beforeTax:
            text.append(_('Applied after tax'))
        if obj.singleUse:
            text.append(_('Single use'))
        if obj.forFirstTimeCustomersOnly:
            text.append(_('First-time customer'))
        if obj.forPreviousCustomersOnly:
            text.append(_('Previous customer'))
        if obj.doorOnly:
            text.append(_('At-the-door only'))
        if obj.customervoucher_set.all().exists():
            text.append(_('Specific customer'))
        if obj.classvoucher_set.all().exists():
            text.append(_('Specific class'))
        if obj.dancetypevoucher_set.all().exists():
            text.append(_('Specific dance type/level'))
        if obj.expirationDate:
            text.append(_('Expires {date}'.format(date=obj.expirationDate.strftime('%x'))))
        return ', '.join([str(x) for x in text])
    restrictions.short_description = _('Restrictions/Notes')

    def disableVoucher(self, request, queryset):
        rows_updated = queryset.update(disabled=True)
        if rows_updated == 1:
            message_bit = "1 voucher was"
        else:
            message_bit = "%s vouchers were" % rows_updated
        self.message_user(request, "%s successfully disabled." % message_bit)
    disableVoucher.short_description = _('Disable selected Vouchers')

    def enableVoucher(self, request, queryset):
        rows_updated = queryset.update(disabled=False)
        if rows_updated == 1:
            message_bit = "1 voucher was"
        else:
            message_bit = "%s vouchers were" % rows_updated
        self.message_user(request, "%s successfully enabled." % message_bit)
    enableVoucher.short_description = _('Enable selected Vouchers')


# This adds inlines to Invoice without subclassing
admin.site._registry[Invoice].inlines.insert(0, InvoiceVoucherInline)

admin.site.register(VoucherCategory)
admin.site.register(Voucher, VoucherAdmin)
admin.site.unregister(Customer)
admin.site.register(Customer, CustomerAdminWithVouchers)
