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
from polymorphic.admin import PolymorphicParentModelAdmin, PolymorphicChildModelAdmin, PolymorphicChildModelFilter

from danceschool.core.models import Location, Room, StaffMember, EventStaffCategory

from .models import ExpenseItem, ExpenseCategory, RevenueItem, RevenueCategory, RepeatedExpenseRule, LocationRentalInfo, RoomRentalInfo, StaffDefaultWage, StaffMemberWageInfo, GenericRepeatedExpense, TransactionParty
from .forms import ExpenseCategoryWidget
from .autocomplete_light_registry import get_method_list


class ExpenseItemAdminForm(ModelForm):
    payTo = ModelChoiceField(
        queryset=TransactionParty.objects.all(),
        label=_('Pay to'),
        required=True,
        widget=autocomplete.ModelSelect2(
            url='transactionParty-list-autocomplete',
            attrs={
                # This will set the input placeholder attribute:
                'data-placeholder': _('Enter a name or location'),
                # This will set the yourlabs.Autocomplete.minimumCharacters
                # options, the naming conversion is handled by jQuery
                'data-minimum-input-length': 2,
                'data-max-results': 8,
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


class ExpenseItemAdminChangelistForm(ExpenseItemAdminForm):
    ''' Make the payTo field optional. '''

    def __init__(self,*args,**kwargs):
        super(ExpenseItemAdminChangelistForm,self).__init__(*args,**kwargs)
        self.fields['payTo'].required=False


@admin.register(ExpenseItem)
class ExpenseItemAdmin(admin.ModelAdmin):
    form = ExpenseItemAdminForm

    list_display = ('category','expenseStartDate','expenseEndDate','description','hours','total','approved','paid','reimbursement','payToName','paymentMethod')
    list_editable = ('approved','paid','paymentMethod')
    search_fields = ('description','comments','=category__name','=payTo__name')
    list_filter = ('category','approved','paid','paymentMethod','reimbursement','payTo',('accrualDate',DateRangeFilter),('paymentDate',DateRangeFilter),('submissionDate',DateRangeFilter),'expenseRule')
    readonly_fields = ('submissionUser','expenseRule','expenseStartDate','expenseEndDate')
    actions = ('approveExpense','unapproveExpense')

    fieldsets = (
        (_('Basic Info'), {
            'fields': ('category','description','payTo','hours','wageRate','total','adjustments','fees','reimbursement','comments')
        }),
        (_('File Attachment (optional)'), {
            'fields': ('attachment',)
        }),
        (_('Approval/Payment Status'), {
            'classes': ('collapse',),
            'fields': ('periodStart','periodEnd','approved','approvalDate','paid','paymentDate','paymentMethod','accrualDate','expenseRule','event')
        }),
    )

    def payToName(self,obj):
        ''' Avoids widget issues with list_display '''
        return obj.payTo.name
    payToName.short_description = _('Pay to')

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
        return ExpenseItemAdminChangelistForm

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
    receivedFrom = ModelChoiceField(
        queryset=TransactionParty.objects.all(),
        label=_('Received from'),
        required=False,
        widget=autocomplete.ModelSelect2(
            url='transactionParty-list-autocomplete',
            attrs={
                # This will set the input placeholder attribute:
                'data-placeholder': _('Enter a name or location'),
                # This will set the yourlabs.Autocomplete.minimumCharacters
                # options, the naming conversion is handled by jQuery
                'data-minimum-input-length': 2,
                'data-max-results': 8,
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


@admin.register(RevenueItem)
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
            'fields': ('category','description','grossTotal','total','adjustments','fees','netRevenue','paymentMethod','receivedFrom','invoiceNumber','comments')
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


@admin.register(TransactionParty)
class TransactionPartyAdmin(admin.ModelAdmin):
    list_display = ('name','user_exists','staffmember_exists','location_exists')
    search_fields = ('name',)
    exclude = []

    def user_exists(self,obj):
        return (obj.user is not None)
    user_exists.short_description = _('User?')
    user_exists.boolean = True

    def staffmember_exists(self,obj):
        return (obj.staffMember is not None)
    staffmember_exists.short_description = _('Staff member?')
    staffmember_exists.boolean = True

    def location_exists(self,obj):
        return (obj.location is not None)
    location_exists.short_description = _('Location?')
    location_exists.boolean = True


class LocationRentalInfoInline(admin.StackedInline):
    model = LocationRentalInfo
    extra = 1
    fields = (('rentalRate','applyRateRule'),('dayStarts','weekStarts','monthStarts'),('advanceDays','advanceDaysReference','priorDays','priorDaysReference'),'disabled')
    classes = ('collapse',)

    def has_add_permission(self, request, obj=None):
        return False


class RoomRentalInfoInline(admin.StackedInline):
    model = RoomRentalInfo
    extra = 1
    fields = (('rentalRate','applyRateRule'),('dayStarts','weekStarts','monthStarts'),('advanceDays','advanceDaysReference','priorDays','priorDaysReference'),'disabled')
    classes = ('collapse',)

    def has_add_permission(self, request, obj=None):
        return False


class StaffDefaultWageInline(admin.StackedInline):
    model = StaffDefaultWage
    extra = 1
    fields = (('rentalRate','applyRateRule'),('dayStarts','weekStarts','monthStarts'),('advanceDays','advanceDaysReference','priorDays','priorDaysReference'),'disabled')
    classes = ('collapse',)

    def has_add_permission(self, request, obj=None):
        return False


class StaffMemberWageInfoInline(admin.StackedInline):
    model = StaffMemberWageInfo
    min_num = 0
    extra = 0
    fields = (('category','rentalRate','applyRateRule'),('dayStarts','weekStarts','monthStarts'),('advanceDays','advanceDaysReference','priorDays','priorDaysReference'),'disabled')
    classes = ('collapse',)


def resetStaffCompensationInfo(self, request, queryset):
    '''
    This action is added to the list for staff member to permit bulk
    reseting to category defaults of compensation information for staff members.
    '''
    selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
    ct = ContentType.objects.get_for_model(queryset.model)
    return HttpResponseRedirect(reverse('resetCompensationRules') + "?ct=%s&ids=%s" % (ct.pk, ",".join(selected)))


resetStaffCompensationInfo.short_description = _('Reset compensation rules')


def updateStaffCompensationInfo(self, request, queryset):
    '''
    This action is added to the list for staff member to permit bulk
    updating of compensation information for staff members.
    '''
    selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
    ct = ContentType.objects.get_for_model(queryset.model)
    return HttpResponseRedirect(reverse('updateCompensationRules') + "?ct=%s&ids=%s" % (ct.pk, ",".join(selected)))


updateStaffCompensationInfo.short_description = _('Update compensation rules')


class RepeatedExpenseRuleChildAdmin(PolymorphicChildModelAdmin):
    """ Base admin class for all child models """
    base_model = RepeatedExpenseRule
    readonly_fields = ('lastRun',)

    # By using these `base_...` attributes instead of the regular ModelAdmin `form` and `fieldsets`,
    # the additional fields of the child models are automatically added to the admin form.
    base_fieldsets = (
        (None, {
            'fields': ('rentalRate','applyRateRule','disabled','lastRun')
        }),
        (_('Generation rules'),{
            'fields': ('dayStarts','weekStarts','monthStarts',('advanceDays','advanceDaysReference'),('priorDays','priorDaysReference')),
        }),
        (_('Start and End Date (optional)'), {
            'fields': ('startDate','endDate')
        }),
    )

    def get_fieldsets(self, request, obj=None):
        ''' Override polymorphic default to put the subclass-specific fields first '''
        # If subclass declares fieldsets, this is respected
        if (hasattr(self, 'declared_fieldset') and self.declared_fieldsets) \
           or not self.base_fieldsets:
            return super(PolymorphicChildModelAdmin, self).get_fieldsets(request, obj)

        other_fields = self.get_subclass_fields(request, obj)

        if other_fields:
            return (
                (self.extra_fieldset_title, {'fields': other_fields}),
            ) + self.base_fieldsets
        else:
            return self.base_fieldsets


@admin.register(LocationRentalInfo)
class LocationRentalInfoAdmin(RepeatedExpenseRuleChildAdmin):
    base_model = LocationRentalInfo
    extra_fieldset_title = None


@admin.register(RoomRentalInfo)
class RoomRentalInfoAdmin(RepeatedExpenseRuleChildAdmin):
    base_model = RoomRentalInfo
    extra_fieldset_title = None


@admin.register(StaffMemberWageInfo)
class StaffMemberWageInfoAdmin(RepeatedExpenseRuleChildAdmin):
    base_model = StaffMemberWageInfo
    extra_fieldset_title = None


class GenericRepeatedExpenseAdminForm(ModelForm):

    paymentMethod = autocomplete.Select2ListCreateChoiceField(
        choice_list=get_method_list,
        required=False,
        widget=autocomplete.ListSelect2(url='paymentMethod-list-autocomplete')
    )

    def __init__(self,*args,**kwargs):
        super(GenericRepeatedExpenseAdminForm,self).__init__(*args,**kwargs)

        updatedChoices = RepeatedExpenseRule.RateRuleChoices.choices
        index = [x[0] for x in updatedChoices].index('D')
        updatedChoices = updatedChoices[:index] + (('D',_('Per day')),) + updatedChoices[index + 1:]
        self.fields.get('applyRateRule').choices = updatedChoices


@admin.register(GenericRepeatedExpense)
class GenericRepeatedExpenseAdmin(RepeatedExpenseRuleChildAdmin):
    base_model = GenericRepeatedExpense
    base_form = GenericRepeatedExpenseAdminForm

    base_fieldsets = (
        (None, {
            'fields': ('name','payTo','rentalRate','applyRateRule','category','disabled','lastRun')
        }),
        (_('Generation rules'),{
            'fields': ('dayStarts','weekStarts','monthStarts',('advanceDays','advanceDaysReference'),('priorDays','priorDaysReference')),
        }),
        (_('Start and End Date (optional)'), {
            'fields': ('startDate','endDate'),
            'classes': ('collapse',)
        }),
        (_('Automated approval'),{
            'fields': ('markApproved','markPaid','paymentMethod',),
            'classes': ('collapse',)
        }),
    )


@admin.register(RepeatedExpenseRule)
class RepeatedExpenseRuleAdmin(PolymorphicParentModelAdmin):
    base_model = RepeatedExpenseRule
    child_models = (LocationRentalInfo,RoomRentalInfo,StaffMemberWageInfo,GenericRepeatedExpense)
    polymorphic_list = True

    list_display = ('ruleName','applyRateRule','rentalRate','_enabled','lastRun')
    list_filter = (PolymorphicChildModelFilter,'applyRateRule','startDate','endDate','lastRun')

    actions = ('disableRules','enableRules','generateExpenses')

    def _enabled(self,obj):
        ''' Change the label '''
        return obj.disabled is False
    _enabled.short_description = _('Enabled')
    _enabled.boolean = True

    def disableRules(self, request, queryset):
        rows_updated = queryset.update(disabled=True)
        if rows_updated == 1:
            message_bit = "1 rule was"
        else:
            message_bit = "%s rules were" % rows_updated
        self.message_user(request, "%s successfully disabled." % message_bit)
    disableRules.short_description = _('Disable selected repeated expense rules')

    def enableRules(self, request, queryset):
        rows_updated = queryset.update(disabled=False)
        if rows_updated == 1:
            message_bit = "1 rule was"
        else:
            message_bit = "%s rules were" % rows_updated
        self.message_user(request, "%s successfully enabled." % message_bit)
    enableRules.short_description = _('Enable selected repeated expense rules')

    def generateExpenses(self, request, queryset):
        rule_count = len(queryset)
        generate_count = 0
        for q in queryset:
            generate_count += q.generateExpenses(request=request)
        message_bit = 'Successfully generated %s expense item%s from %s rule%s.' % (
            generate_count, 's' if generate_count != 1 else '', rule_count, 's' if rule_count != 1 else '')
        self.message_user(request, message_bit)

    generateExpenses.short_description = _('Generate expenses for selected repeated expense rules')


admin.site.register(ExpenseCategory)
admin.site.register(RevenueCategory)

# This adds inlines to Location and Room without subclassing
admin.site._registry[Location].inlines.insert(0,LocationRentalInfoInline)
admin.site._registry[Room].inlines.insert(0,RoomRentalInfoInline)
admin.site._registry[StaffMember].inlines.insert(0,StaffMemberWageInfoInline)
admin.site._registry[StaffMember].actions.insert(0,resetStaffCompensationInfo)
admin.site._registry[StaffMember].actions.insert(0,updateStaffCompensationInfo)
admin.site._registry[EventStaffCategory].inlines.insert(0,StaffDefaultWageInline)
