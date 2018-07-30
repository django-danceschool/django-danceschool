from django.contrib import admin
from django.forms import ModelForm, ModelChoiceField, TextInput
from django.utils.translation import ugettext_lazy as _

from dal import autocomplete

from danceschool.core.models import Customer, Registration, TemporaryRegistration
from danceschool.core.admin import CustomerAdmin

from .models import VoucherCategory, Voucher, DanceTypeVoucher, ClassVoucher, CustomerGroupVoucher, CustomerVoucher, VoucherUse, TemporaryVoucherUse, VoucherCredit


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


class CustomerGroupVoucherInline(admin.StackedInline):
    model = CustomerGroupVoucher
    extra = 1
    classes = ['collapse',]


class CustomerVoucherInline(admin.StackedInline):
    model = CustomerVoucher
    form = CustomerVoucherInlineForm
    extra = 1
    classes = ['collapse',]


class CustomerAdminWithVouchers(CustomerAdmin):
    inlines = CustomerAdmin.inlines + [CustomerVoucherInline]


class RegistrationVoucherInline(admin.TabularInline):
    model = VoucherUse
    extra = 0
    readonly_fields = ['voucher','amount']

    # Prevents adding new voucher uses without going through
    # the standard registration process
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class TemporaryRegistrationVoucherInline(admin.TabularInline):
    model = TemporaryVoucherUse
    extra = 0
    readonly_fields = ['voucher','amount']

    # Prevents adding new voucher uses without going through
    # the standard registration process
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class DanceTypeVoucherInline(admin.StackedInline):
    model = DanceTypeVoucher
    extra = 1
    classes = ['collapse',]


class ClassVoucherInline(admin.StackedInline):
    model = ClassVoucher
    extra = 1
    classes = ['collapse',]


class VoucherUseInline(admin.TabularInline):
    model = VoucherUse
    extra = 0
    readonly_fields = ['registration','amount']

    # Prevents adding new voucher uses without going through
    # the standard registration process.
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class VoucherCreditInlineForm(ModelForm):

    class Meta:
        widgets = {
            'description': TextInput,
        }


class VoucherCreditInline(admin.TabularInline):
    model = VoucherCredit
    extra = 1
    fields = ['amount', 'description','creationDate']
    readonly_fields = ['creationDate',]

    form = VoucherCreditInlineForm


class VoucherAdmin(admin.ModelAdmin):
    inlines = [DanceTypeVoucherInline,ClassVoucherInline,CustomerGroupVoucherInline,CustomerVoucherInline,VoucherUseInline,VoucherCreditInline]
    list_display = ['voucherId','name','category','amountLeft','maxAmountPerUse','expirationDate','isEnabled','restrictions']
    list_filter = ['category','expirationDate','disabled','forFirstTimeCustomersOnly','forPreviousCustomersOnly']
    search_fields = ['voucherId','name','description']
    readonly_fields = ['refundAmount','creationDate']
    actions = ['enableVoucher','disableVoucher']

    fieldsets = (
        (None, {
            'fields': (('voucherId','category'),'name','description',('originalAmount','maxAmountPerUse'),),
        }),
        (_('Voucher Restrictions'), {
            'fields': ('expirationDate',('singleUse','forFirstTimeCustomersOnly','forPreviousCustomersOnly','disabled')),
        }),
        (_('Other Info'), {
            'classes': ('collapse',),
            'fields': ('creationDate','refundAmount'),
        }),
    )

    def isEnabled(self,obj):
        return obj.disabled is False
    isEnabled.short_description = _('Enabled')
    isEnabled.boolean = True

    def restrictions(self,obj):
        text = []
        if obj.singleUse:
            text.append(_('Single use'))
        if obj.forFirstTimeCustomersOnly:
            text.append(_('First-time customer'))
        if obj.forPreviousCustomersOnly:
            text.append(_('Previous customer'))
        if obj.customervoucher_set.all().exists():
            text.append(_('Specific customer'))
        if obj.classvoucher_set.all().exists():
            text.append(_('Specific class'))
        if obj.dancetypevoucher_set.all().exists():
            text.append(_('Specific dance type/level'))
        return ', '.join([str(x) for x in text])
    restrictions.short_description = _('Restrictions')

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


# This adds inlines to Registration and TemporaryRegistration without subclassing
admin.site._registry[Registration].inlines.insert(0,RegistrationVoucherInline)
admin.site._registry[TemporaryRegistration].inlines.insert(0,TemporaryRegistrationVoucherInline)

admin.site.register(VoucherCategory)
admin.site.register(Voucher,VoucherAdmin)
admin.site.unregister(Customer)
admin.site.register(Customer,CustomerAdminWithVouchers)
