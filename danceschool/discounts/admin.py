from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

from .models import DiscountCombo, DiscountComboComponent, PointGroup, PricingTierGroup, RegistrationDiscount, TemporaryRegistrationDiscount
from danceschool.core.models import Registration, TemporaryRegistration, PricingTier


class DiscountComboComponentInline(admin.StackedInline):
    model = DiscountComboComponent
    extra = 1


class DiscountComboAdmin(admin.ModelAdmin):
    inlines = [DiscountComboComponentInline,]

    list_display = ('name','discountType','newCustomersOnly','active')
    list_filter = ('discountType','newCustomersOnly','active')
    ordering = ('name',)

    fieldsets = (
        (None, {
            'fields': ('name','active','newCustomersOnly','discountType',)
        }),
        (_('For Flat-Price Discounts'), {
            'fields': ('onlineStudentPrice','doorStudentPrice','onlineGeneralPrice','doorGeneralPrice'),
        }),
        (_('For Dollar Discounts'), {
            'fields': ('dollarDiscount',),
        }),
        (_('For Percentage Discounts'), {
            'fields': ('percentDiscount','percentUniversallyApplied'),
        }),
    )


class RegistrationDiscountInline(admin.TabularInline):
    model = RegistrationDiscount
    readonly_fields = ('discount', 'discountAmount')
    extra = 0

    # Prevents adding new discounts without going through
    # the standard registration process
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class TemporaryRegistrationDiscountInline(admin.TabularInline):
    model = TemporaryRegistrationDiscount
    readonly_fields = ('discount', 'discountAmount')
    extra = 0

    # Prevents adding new discounts without going through
    # the standard registration process
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PricingTierGroupInline(admin.TabularInline):
    model = PricingTierGroup
    extra = 0
    verbose_name = _('pricing tier discount group')
    verbose_name_plural = _('pricing tier discount groups')


# This adds the inlines to Registration and TemporyRegistration without subclassing
admin.site._registry[Registration].inlines.insert(0,RegistrationDiscountInline)
admin.site._registry[TemporaryRegistration].inlines.insert(0,TemporaryRegistrationDiscountInline)
admin.site._registry[PricingTier].inlines.insert(0,PricingTierGroupInline)

admin.site.register(DiscountCombo,DiscountComboAdmin)
admin.site.register(PointGroup)
