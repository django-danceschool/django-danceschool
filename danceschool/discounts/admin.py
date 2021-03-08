from django.forms import ModelForm, ModelChoiceField
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from dal import autocomplete

from .models import (
    DiscountCategory, DiscountCombo, DiscountComboComponent,
    PointGroup, PricingTierGroup, RegistrationDiscount,
    CustomerGroupDiscount, CustomerDiscount
)
from danceschool.core.models import (
    Registration, Registration, PricingTier, Customer
)


class DiscountCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'order', 'cannotCombine')
    list_editable = ('order', )
    list_filter = ('cannotCombine', )
    search_fields = ('name', )


class DiscountComboComponentInline(admin.StackedInline):
    model = DiscountComboComponent
    extra = 1
    fields = (('pointGroup', 'quantity', ), 'allWithinPointGroup', ('level', 'weekday'), )


class CustomerDiscountInlineForm(ModelForm):
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
        model = CustomerDiscount
        exclude = []

    class Media:
        js = (
            'admin/js/vendor/jquery/jquery.min.js',
            'admin/js/jquery.init.js',
        )


class CustomerGroupDiscountInline(admin.StackedInline):
    model = CustomerGroupDiscount
    extra = 1
    classes = ['collapse', ]


class CustomerDiscountInline(admin.StackedInline):
    model = CustomerDiscount
    form = CustomerDiscountInlineForm
    extra = 1
    classes = ['collapse', ]


class DiscountComboAdminForm(ModelForm):

    class Meta:
        model = DiscountCombo
        exclude = []

    class Media:
        js = (
            'admin/js/vendor/jquery/jquery.min.js',
            'js/discountcombo_collapsetypes.js',
        )


class DiscountComboAdmin(admin.ModelAdmin):
    inlines = [
        DiscountComboComponentInline, CustomerGroupDiscountInline,
        CustomerDiscountInline
    ]
    form = DiscountComboAdminForm

    list_display = (
        'name', 'category', 'discountType', 'active', 'expirationDate',
        'restrictions'
    )
    list_filter = (
        'category', 'discountType', 'active', 'newCustomersOnly', 'expirationDate'
    )
    ordering = ('name', )
    actions = ['enableDiscount', 'disableDiscount']

    fieldsets = (
        (None, {
            'fields': (
                'name', 'category',
                ('active', 'expirationDate'),
                'newCustomersOnly', 'studentsOnly', 'daysInAdvanceRequired',
                'firstXRegistered', 'customerMatchRequired', 'discountType',
            )
        }),
        (_('Flat-Price Discount (in default currency)'), {
            'classes': ('type_flatPrice', ),
            'fields': ('onlinePrice', 'doorPrice'),
        }),
        (_('Dollar Discount (in default currency)'), {
            'classes': ('type_dollarDiscount', ),
            'fields': ('dollarDiscount', ),
        }),
        (_('Percentage Discount'), {
            'classes': ('type_percentageDiscount', ),
            'fields': ('percentDiscount', 'percentUniversallyApplied'),
        }),
    )

    def restrictions(self, obj):
        text = []
        if obj.studentsOnly:
            text.append(_('Students only'))
        if obj.newCustomersOnly:
            text.append(_('First-time customer'))
        if obj.daysInAdvanceRequired:
            text.append(_('%s day advance registration' % obj.daysInAdvanceRequired))
        if obj.firstXRegistered:
            text.append(_('First %s to register' % obj.firstXRegistered))
        if obj.customerMatchRequired:
            text.append(_('Primary customer registrations only'))
        return ', '.join([str(x) for x in text])
    restrictions.short_description = _('Restrictions')

    def disableDiscount(self, request, queryset):
        rows_updated = queryset.update(active=False)
        if rows_updated == 1:
            message_bit = "1 discount was"
        else:
            message_bit = "%s discounts were" % rows_updated
        self.message_user(request, "%s successfully disabled." % message_bit)
    disableDiscount.short_description = _('Disable selected Discounts')

    def enableDiscount(self, request, queryset):
        rows_updated = queryset.update(active=True)
        if rows_updated == 1:
            message_bit = "1 discount was"
        else:
            message_bit = "%s discounts were" % rows_updated
        self.message_user(request, "%s successfully enabled." % message_bit)
    enableDiscount.short_description = _('Enable selected Discounts')


class RegistrationDiscountInline(admin.TabularInline):
    model = RegistrationDiscount
    readonly_fields = ('discount', 'discountAmount')
    exclude = ('applied',)
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


class PointGroupAdmin(admin.ModelAdmin):
    inlines = (PricingTierGroupInline, )

    list_display = ('name', )
    ordering = ('name', )


# This adds the inlines to Registration and PricingTier without subclassing
admin.site._registry[Registration].inlines.insert(0, RegistrationDiscountInline)
admin.site._registry[PricingTier].inlines.insert(0, PricingTierGroupInline)

admin.site.register(DiscountCategory, DiscountCategoryAdmin)
admin.site.register(DiscountCombo, DiscountComboAdmin)
admin.site.register(PointGroup, PointGroupAdmin)
