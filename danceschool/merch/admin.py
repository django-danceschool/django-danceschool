from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse


from .models import (
    MerchItem, MerchItemVariant, MerchOrder, MerchOrderItem,
    MerchQuantityAdjustment
)


class MerchItemVariantForm(forms.ModelForm):
    '''
    This custom admin form causes the newQuantity field to be displayed in
    place of the originalQuantity field.  That way, the user can update the
    inventory of merch without having to go through the full record of inventory
    adjustments.  The form save() method handles the logic of updating the
    underlying inventory data appropriately.
    '''

    newQuantity = forms.IntegerField(
        label=_('Current quantity'), required=True,
        help_text=_(
            'Enter the total current inventory.  If changed, the inventory ' +
            'records will be automatically adjusted.'
        ),
    )

    def __init__(self, **kwargs):
        '''
        Hide the originalQuantity field and set the newQuantity field to reflect
        current inventory levels.
        '''
        super().__init__(**kwargs)

        self.fields.get('originalQuantity').widget = forms.HiddenInput()

        if self.instance.pk:
            self._initial_inventory = self.instance.currentInventory
        else:
            self._initial_inventory = 0
            self.fields.get('originalQuantity').initial = 0
            
        self.fields.get('newQuantity').initial = self._initial_inventory

    def save(self, commit=True):
        ''' If the quantity has been updated, then update inventory records. '''
        newQuantity = self.cleaned_data.get('newQuantity', None)

        if self._initial_inventory != newQuantity:
            if not self.instance.pk:
                super().save(commit=False)
                self.instance.originalQuantity = newQuantity
            else:
                MerchQuantityAdjustment.objects.create(
                    variant=self.instance,
                    amount=(newQuantity - self._initial_inventory)
                )

        return super().save(commit=commit)

    class Meta:
        model = MerchItemVariant
        fields = '__all__'
    


class MerchItemVariantInline(admin.StackedInline):
    model = MerchItemVariant
    form = MerchItemVariantForm
    extra = 1
    fields = (
        ('name', 'sku', 'price',),
        'photo',
        'newQuantity',
        'originalQuantity',
    )


@admin.register(MerchItem)
class MerchItemAdmin(admin.ModelAdmin):
    readonly_fields = ('creationDate', 'numVariants',)
    list_display = ('name', 'defaultPrice', 'numVariants', 'disabled')
    list_filtered = ('disabled',)
    list_editable = ('disabled',)
    search_fields = ('name', 'description')

    fields = [
        'name', 'description', 'defaultPrice', 'salesTaxRate',
        'photo', 'disabled', 'creationDate'
        ]

    inlines = [MerchItemVariantInline,]


class MerchOrderItemInline(admin.TabularInline):
    model = MerchOrderItem
    extra = 1

    readonly_fields = ('invoiceItem',)
    submitted_readonly_fields = ('item', 'quantity', 'invoiceItem')
    fields = ('item', 'quantity', 'invoiceItem')

    def has_add_permission(self, request, obj=None):
        '''
        MerchOrderItems can only be added when an order is unsubmitted.
        '''
        if obj and not obj.itemsEditable:
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        '''
        MerchOrderItems can only be deleted when an order is unsubmitted.
        '''
        if obj and not obj.itemsEditable:
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        if obj and not obj.itemsEditable:
            return self.submitted_readonly_fields
        return self.readonly_fields

    
@admin.register(MerchOrder)
class MerchOrderAdmin(admin.ModelAdmin):
    list_display = ('getInvoiceId', 'status', 'getInvoiceTotal', 'getInvoiceStatus', 'creationDate')
    list_editable = ('status',)
    search_fields = ('items__name', 'items__description',)
    readonly_fields = ('invoiceLink', 'creationDate', 'lastModified')
    list_filter = ('status', 'creationDate', 'lastModified',)

    fieldsets = (
        (None, {
            'fields': ('status', 'invoiceLink', 'creationDate', 'lastModified'),
        }),
        (_('Additional data'), {
            'classes': ('collapse', ),
            'fields': ('data',),
        }),
    )


    inlines = (MerchOrderItemInline,)

    def getInvoiceId(self, obj):
        return getattr(obj.invoice, 'id', '')
    getInvoiceId.admin_order_field  = 'invoice__id'
    getInvoiceId.short_description = _('ID')

    def getInvoiceTotal(self, obj):
        return getattr(obj.invoice, 'total', None)
    getInvoiceTotal.admin_order_field  = 'invoice__total'
    getInvoiceTotal.short_description = _('Invoice Total')
    
    def getInvoiceStatus(self, obj):
        status = getattr(obj.invoice, 'get_status_display', None)
        if status:
            return status()
    getInvoiceStatus.admin_order_field  = 'invoice__status'
    getInvoiceStatus.short_description = _('Invoice Status')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('invoice')

    def get_admin_change_link(self, app_label, model_name, obj_id, name):
        url = reverse('admin:%s_%s_change' % (app_label, model_name),
                      args=(obj_id, ))
        return format_html('<a href="%s">%s</a>' % (
            url, str(name)
        ))

    def invoiceLink(self, obj):
        if obj.invoice:
            return self.get_admin_change_link(
                'core', 'invoice', obj.invoice.id, _('Invoice')
            )
    invoiceLink.allow_tags = True
    invoiceLink.short_description = _('Invoice')
