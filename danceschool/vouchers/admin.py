from django.contrib import admin
from django.forms import ModelForm, ModelChoiceField, TextInput
from django.utils.translation import ugettext_lazy as _

from dal import autocomplete

from danceschool.core.models import Customer, Registration, TemporaryRegistration
from danceschool.core.admin import CustomerAdmin

from .models import VoucherCategory, Voucher, DanceTypeVoucher, ClassVoucher, CustomerVoucher, VoucherUse, TemporaryVoucherUse, VoucherCredit


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


class CustomerVoucherInline(admin.StackedInline):
    model = CustomerVoucher
    form = CustomerVoucherInlineForm
    extra = 1


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


class ClassVoucherInline(admin.StackedInline):
    model = ClassVoucher
    extra = 1


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
    inlines = [DanceTypeVoucherInline,ClassVoucherInline,CustomerVoucherInline,VoucherUseInline,VoucherCreditInline]
    list_display = ['voucherId','name','category','description','originalAmount','expirationDate','forFirstTimeCustomersOnly','forPreviousCustomersOnly']
    list_filter = ['category','expirationDate','forFirstTimeCustomersOnly','forPreviousCustomersOnly']
    search_fields = ['voucherId','name','type',]
    readonly_fields = ['refundAmount','creationDate']

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


# This adds inlines to Registration and TemporaryRegistration without subclassing
admin.site._registry[Registration].inlines.insert(0,RegistrationVoucherInline)
admin.site._registry[TemporaryRegistration].inlines.insert(0,TemporaryRegistrationVoucherInline)

admin.site.register(VoucherCategory)
admin.site.register(Voucher,VoucherAdmin)
admin.site.unregister(Customer)
admin.site.register(Customer,CustomerAdminWithVouchers)
