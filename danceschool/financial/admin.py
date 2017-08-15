from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.utils.html import format_html
from django.forms import ModelForm, ModelChoiceField
from django.utils.translation import ugettext_lazy as _
from django.http import HttpResponseRedirect

from dal import autocomplete
from daterange_filter.filter import DateRangeFilter

from danceschool.core.models import Location, Room, StaffMember, Instructor

from .models import ExpenseItem, ExpenseCategory, RevenueItem, RevenueCategory, LocationRentalInfo, RoomRentalInfo, StaffMemberWageInfo
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
    paymentMethod = autocomplete.Select2ListCreateChoiceField(
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
    search_fields = ('description','comments','=payToUser__first_name','=payToUser__last_name','=payToLocation__name')
    list_filter = ('category','approved','paid','paymentMethod','reimbursement','payToLocation',('accrualDate',DateRangeFilter),('paymentDate',DateRangeFilter),('submissionDate',DateRangeFilter))
    readonly_fields = ('submissionUser',)
    actions = ('approveExpense','unapproveExpense')

    fieldsets = (
        (_('Basic Info'), {
            'fields': ('category','description','hours','wageRate','total','adjustments','fees','reimbursement','comments')
        }),
        (_('File Attachment (optional)'), {
            'fields': ('attachment',)
        }),
        (_('Approval/Payment Status'), {
            'classes': ('collapse',),
            'fields': ('periodStart','periodEnd','approved','approvalDate','paid','paymentDate','paymentMethod','accrualDate','expenseRule','event','payToUser','payToLocation','payToName')
        }),
    )

    def approveExpense(self, request, queryset):
        rows_updated = queryset.update(approved=True)
        if rows_updated == 1:
            message_bit = "1 expense item was"
        else:
            message_bit = "%s expense items were" % rows_updated
        self.message_user(request, "%s successfully marked as approved." % message_bit)
    approveExpense.short_description = _('Mark Expense Items as approved')

    def unapproveExpense(self, request, queryset):
        rows_updated = queryset.update(approved=False)
        if rows_updated == 1:
            message_bit = "1 expense item was"
        else:
            message_bit = "%s expense items were" % rows_updated
        self.message_user(request, "%s successfully marked as not approved." % message_bit)
    unapproveExpense.short_description = _('Mark Expense Items as not approved')

    def get_changelist_form(self, request, **kwargs):
        ''' Ensures that the autocomplete view works for payment methods. '''
        return ExpenseItemAdminForm

    def save_model(self,request,obj,form,change):
        obj.submissionUser = request.user
        obj.save()

    class Media:
        js = ('js/update_task_wages.js',)


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
    actions = ('markReceived','markNotReceived')

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
            return self.get_admin_change_link('core','invoice',obj.invoiceItem.invoice.id,_('Invoice'))
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

    def markReceived(self, request, queryset):
        rows_updated = queryset.update(received=True)
        if rows_updated == 1:
            message_bit = "1 revenue item was"
        else:
            message_bit = "%s revenue items were" % rows_updated
        self.message_user(request, "%s successfully marked as received." % message_bit)
    markReceived.short_description = _('Mark Revenue Items as received')

    def markNotReceived(self, request, queryset):
        rows_updated = queryset.update(received=False)
        if rows_updated == 1:
            message_bit = "1 revenue item was"
        else:
            message_bit = "%s revenue items were" % rows_updated
        self.message_user(request, "%s successfully marked as not received." % message_bit)
    markNotReceived.short_description = _('Mark Revenue Items as not received')

    def save_model(self,request,obj,form,change):
        obj.submissionUser = request.user
        obj.save()


class LocationRentalInfoInline(admin.StackedInline):
    model = LocationRentalInfo
    extra = 1
    fields = (('rentalRate','applyRateRule'),('dayStarts','weekStarts','monthStarts'),('advanceDays','priorDays'))
    classes = ('collapse',)

    def has_add_permission(self, request, obj=None):
        return False


class RoomRentalInfoInline(admin.StackedInline):
    model = RoomRentalInfo
    extra = 1
    fields = (('rentalRate','applyRateRule'),('dayStarts','weekStarts','monthStarts'),('advanceDays','priorDays'))

    def has_add_permission(self, request, obj=None):
        return False


class StaffMemberWageInfoInline(admin.StackedInline):
    model = StaffMemberWageInfo
    min_num = 1
    extra = 0
    fields = (('category','rentalRate','applyRateRule'),('dayStarts','weekStarts','monthStarts'),('advanceDays','priorDays'))
    classes = ('collapse',)


def updateStaffCompensationInfo(self, request, queryset):
    '''
    This action is added to the list for instructors to permit bulk
    updating of compensation information for staff members.
    '''
    selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
    ct = ContentType.objects.get_for_model(queryset.model)
    return HttpResponseRedirect(reverse('updateCompensationRules') + "?ct=%s&ids=%s" % (ct.pk, ",".join(selected)))


updateStaffCompensationInfo.short_description = _('Update compensation rules')


admin.site.register(ExpenseItem,ExpenseItemAdmin)
admin.site.register(ExpenseCategory)
admin.site.register(RevenueItem,RevenueItemAdmin)
admin.site.register(RevenueCategory)

# This adds inlines to Location and Room without subclassing
admin.site._registry[Location].inlines.insert(0,LocationRentalInfoInline)
admin.site._registry[Room].inlines.insert(0,RoomRentalInfoInline)
admin.site._registry[StaffMember].inlines.insert(0,StaffMemberWageInfoInline)
admin.site._registry[Instructor].inlines.insert(0,StaffMemberWageInfoInline)
admin.site._registry[StaffMember].actions.insert(0,updateStaffCompensationInfo)
admin.site._registry[Instructor].actions.insert(0,updateStaffCompensationInfo)
