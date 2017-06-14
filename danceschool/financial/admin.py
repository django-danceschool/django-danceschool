from django.contrib import admin
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.utils.html import format_html
from django.forms import ModelForm, ModelChoiceField
from django.utils.translation import ugettext_lazy as _

from dal import autocomplete
from daterange_filter.filter import DateRangeFilter

from .models import ExpenseItem, ExpenseCategory, RevenueItem, RevenueCategory
from .forms import ExpenseCategoryWidget
from .autocomplete_light_registry import get_method_list


class ExpenseItemAdminForm(ModelForm):
    payToUser = ModelChoiceField(
        queryset=User.objects.all(),
        label=_('Pay to this user'),
        required=False,
        widget=autocomplete.ModelSelect2(
            url='autocompleteUser',
            attrs={
                # This will set the input placeholder attribute:
                'data-placeholder': _('Enter a user name'),
                # This will set the yourlabs.Autocomplete.minimumCharacters
                # options, the naming conversion is handled by jQuery
                'data-minimum-input-length': 2,
                'data-max-results': 4,
                'class': 'modern-style',
            }
        )
    )
    paymentMethod = autocomplete.Select2ListChoiceField(
        choice_list=get_method_list,
        required=False,
        widget=autocomplete.ListSelect2(url='paymentMethod-list-autocomplete')
    )

    class Meta:
        model = ExpenseItem
        exclude = []
        widgets = {
            'category': ExpenseCategoryWidget
        }


class ExpenseItemAdmin(admin.ModelAdmin):
    form = ExpenseItemAdminForm

    list_display = ('category','description','hours','total','approved','paid','reimbursement','payTo','paymentMethod')
    list_editable = ('approved','paid','paymentMethod')
    search_fields = ('description','comments','=payToUser__first_name','=payToUser__last_name')
    list_filter = ('category','approved','paid','paymentMethod','reimbursement','payToLocation',('accrualDate',DateRangeFilter),('paymentDate',DateRangeFilter),('submissionDate',DateRangeFilter))
    readonly_fields = ('submissionUser',)

    fieldsets = (
        (_('Basic Info'), {
            'fields': ('category','description','hours','wageRate','total','adjustments','fees','reimbursement','comments')
        }),
        (_('File Attachment (optional)'), {
            'fields': ('attachment',)
        }),
        (_('Approval/Payment Status'), {
            'classes': ('collapse',),
            'fields': ('approved','approvalDate','paid','paymentDate','paymentMethod','accrualDate','eventstaffmember','event','payToUser','payToLocation','payToName')
        }),
    )

    class Media:
        js = ('js/update_task_wages.js',)

    def save_model(self,request,obj,form,change):
        obj.submissionUser = request.user
        obj.save()


class RevenueItemAdminForm(ModelForm):
    currentlyHeldBy = ModelChoiceField(
        queryset=User.objects.filter(Q(staffmember__isnull=False) | Q(is_staff=True)),
        label=_('Cash currently in possession of'),
        required=False,
        widget=autocomplete.ModelSelect2(
            url='autocompleteUser',
            attrs={
                # This will set the input placeholder attribute:
                'data-placeholder': _('Enter a user name'),
                # This will set the yourlabs.Autocomplete.minimumCharacters
                # options, the naming conversion is handled by jQuery
                'data-minimum-input-length': 2,
                'data-max-results': 4,
                'class': 'modern-style',
            }
        )
    )
    paymentMethod = autocomplete.Select2ListChoiceField(
        choice_list=get_method_list,
        required=False,
        widget=autocomplete.ListSelect2(url='paymentMethod-list-autocomplete')
    )


    class Meta:
        model = RevenueItem
        exclude = []


class RevenueItemAdmin(admin.ModelAdmin):
    form = RevenueItemAdminForm

    list_display = ('description','category','grossTotal','total','adjustments','netRevenue','received','receivedDate','invoiceLink')
    list_editable = ('received',)
    search_fields = ('description','comments','invoiceItem__id','invoiceItem__invoice__id')
    list_filter = ('category','received','paymentMethod',('receivedDate',DateRangeFilter),('accrualDate',DateRangeFilter),('submissionDate',DateRangeFilter))
    readonly_fields = ('netRevenue','submissionUserLink','relatedRevItemsLink','eventLink','paymentMethod','invoiceNumber','invoiceLink')

    fieldsets = (
        (_('Basic Info'), {
            'fields': ('category','description','grossTotal','total','adjustments','fees','netRevenue','paymentMethod','receivedFromName','invoiceNumber','comments')
        }),
        (_('Related Items'),{
            'fields': ('relatedRevItemsLink','eventLink','invoiceLink'),
        }),
        (_('File Attachment (optional)'), {
            'fields': ('attachment',)
        }),
        (_('Approval/Payment Status'), {
            'fields': ('submissionUserLink','currentlyHeldBy','received','receivedDate','accrualDate')
        }),
    )

    def user_full_name(self,obj):
        if obj.submissionUser:
            return obj.submissionUser.first_name + ' ' + obj.submissionUser.last_name
        return ''

    def get_admin_change_link(self,app_label, model_name, obj_id, name):
        url = reverse('admin:%s_%s_change' % (app_label, model_name),
                      args=(obj_id,))
        return format_html('<a href="%s">%s</a>' % (
            url, str(name)
        ))

    def relatedRevItemsLink(self,obj):
        link = []
        for item in obj.relatedItems or []:
            link.append(self.get_admin_change_link('financial','revenueitem',item.id,item.__str__()))
            return ', '.join(link)
    relatedRevItemsLink.allow_tags = True
    relatedRevItemsLink.short_description = _('Revenue Items')

    def eventLink(self,obj):
        if obj.eventregistration:
            sr = obj.eventregistration
            return 'Registration: ' + self.get_admin_change_link('core','registration',sr.registration.id,sr.registration.__str__())
        elif obj.event:
            s = obj.event
            return self.get_admin_change_link('core','event',s.id,s.__str__())
    eventLink.allow_tags = True
    eventLink.short_description = _('Series/Event')

    def invoiceLink(self,obj):
        ''' If vouchers app is enabled and there is a voucher, this will link to it. '''
        if hasattr(obj,'invoiceItem') and obj.invoiceItem:
            return self.get_admin_change_link('core','invoice',obj.invoiceItem.invoice.id,obj.invoiceItem.invoice.id)
    invoiceLink.allow_tags = True
    invoiceLink.short_description = _('Invoice')

    def submissionUserLink(self,obj):
        link = []

        if obj.submissionUser:
            u = obj.submissionUser
            link.append(self.get_admin_change_link('auth','user',u.id,u.get_full_name()))
        if obj.submissionDate:
            link.append(str(obj.submissionDate))
        return ', '.join(link)
    submissionUserLink.allow_tags = True
    submissionUserLink.short_description = _('Submitted')

    def save_model(self,request,obj,form,change):
        obj.submissionUser = request.user
        obj.save()


admin.site.register(ExpenseItem,ExpenseItemAdmin)
admin.site.register(ExpenseCategory)
admin.site.register(RevenueItem,RevenueItemAdmin)
admin.site.register(RevenueCategory)
