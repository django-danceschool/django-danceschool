from django.contrib import admin
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.forms import ModelForm, ChoiceField
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy as _

from django_admin_listfilter_dropdown.filters import ChoiceDropdownFilter
from rangefilter.filters import DateRangeFilter

from ..models import Invoice, InvoiceItem


class InvoiceAdminForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Invoices that are already in a finalized type of status cannot be
        # changed to a non-finalized type of status.  This is enforced at the
        # model level; this code just limits the dropdown choices.
        instance = kwargs.get('instance', None)

        if getattr(instance, 'status', None) in [
            Invoice.PaymentStatus.paid, Invoice.PaymentStatus.needsCollection,
            Invoice.PaymentStatus.fullRefund,
        ]:
            limited_choices = [
                x for x in Invoice.PaymentStatus.choices if x[0] in [
                    Invoice.PaymentStatus.paid,
                    Invoice.PaymentStatus.needsCollection,
                    Invoice.PaymentStatus.fullRefund
                ]
            ]
            self.fields['status'] = ChoiceField(
                choices=limited_choices, required=True,
            )

    class Meta:
        model = Invoice
        exclude = []


class InvoiceItemInline(admin.StackedInline):
    model = InvoiceItem
    extra = 0
    add_fields = [('description', 'grossTotal', 'total', 'taxRate', 'taxes', 'fees', 'adjustments'), ]
    fields = ['id', ('description', 'grossTotal', 'total', 'taxRate', 'taxes', 'fees', 'adjustments'), ]
    add_readonly_fields = ['fees', ]
    readonly_fields = ['id', 'grossTotal', 'total', 'taxRate', 'taxes', 'fees']

    def has_add_permission(self, request, obj=None):
        '''
        InvoiceItems can only be added when an invoice's status is preliminary
        or unpaid.
        '''
        if obj and not obj.itemsEditable:
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        '''
        InvoiceItems can only be deleted when an invoice's status is preliminary
        or unpaid.
        '''
        if obj and not obj.itemsEditable:
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        if not obj or getattr(obj, 'itemsEditable', False):
            return self.add_readonly_fields
        return self.readonly_fields

    def get_fields(self, request, obj=None):
        if not obj or getattr(obj, 'itemsEditable', False):
            return self.add_fields
        return super().get_fields(request, obj)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    form = InvoiceAdminForm
    inlines = [InvoiceItemInline, ]
    list_display = [
        'id', 'recipientInfo', 'status', 'outstandingBalance',
        'modifiedDate', 'links'
    ]
    list_filter = [
        ('status', ChoiceDropdownFilter),
        'paidOnline',
        ('creationDate', DateRangeFilter),
        ('modifiedDate', DateRangeFilter)
    ]
    search_fields = ['id', 'comments']
    ordering = ['-modifiedDate', ]
    readonly_fields = [
        'id', 'recipientInfo', 'total', 'adjustments', 'taxes', 'fees',
        'netRevenue', 'outstandingBalance', 'creationDate', 'modifiedDate',
        'links', 'submissionUser', 'collectedByUser'
    ]
    view_on_site = True

    fieldsets = (
        (None, {
            'fields': (
                'id', ('firstName', 'lastName', 'email'), 'comments', 'status',
                'amountPaid', 'outstandingBalance', 'links'
            ),
        }),
        (_('Financial Details'), {
            'classes': ('collapse', ),
            'fields': ('total', 'adjustments', 'taxes', 'fees', 'netRevenue'),
        }),
        (_('Dates'), {
            'classes': ('collapse', ),
            'fields': ('creationDate', 'modifiedDate'),
        }),
        (_('Additional data'), {
            'classes': ('collapse', ),
            'fields': ('submissionUser', 'collectedByUser', 'data'),
        }),
    )

    add_fieldsets = (
        (None, {
            'fields': (
                ('firstName', 'lastName', 'email'), 'comments', 'status',
                'amountPaid',
            ),
        }),
        (_('Additional data'), {
            'classes': ('collapse', ),
            'fields': ('data', ),
        }),
    )

    def emailNotification(self, request, queryset):
        # Allows use of the email view to contact specific customers.
        selected = request.POST.getlist(ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect(
            reverse('sendInvoiceNotifications') +
            "?invoices=%s" % (", ".join(selected))
        )
    emailNotification.short_description = _('Send email notifications for selected invoices')

    actions = ['emailNotification', ]

    def recipientInfo(self, obj):
        if obj.firstName and obj.lastName and obj.email:
            return '%s %s: %s' % (obj.firstName, obj.lastName, obj.email)
        elif obj.email:
            return obj.email
    recipientInfo.short_description = _('Recipient')

    def viewInvoiceLink(self, obj):
        if obj.id:
            change_url = reverse('viewInvoice', args=(obj.id, ))
            return mark_safe(
                '<a href="%s?v=%s">%s</a>' % (
                    change_url, obj.validationString, gettext('View')
                )
            )
    viewInvoiceLink.allow_tags = True
    viewInvoiceLink.short_description = _('Invoice')

    def notificationLink(self, obj):
        if obj.id:
            change_url = reverse('sendInvoiceNotifications', args=(obj.id, ))
            return mark_safe(
                '<a href="%s">%s</a>' % (change_url, gettext('Notify'))
            )
    notificationLink.allow_tags = True
    notificationLink.short_description = _('Invoice notification')

    def registrationLink(self, obj):
        if getattr(obj, 'registration', None):
            change_url = reverse('admin:core_registration_change', args=(obj.registration.id, ))
            return mark_safe(
                '<a href="%s">%s</a>' % (change_url, gettext('Registration'))
            )
    registrationLink.allow_tags = True
    registrationLink.short_description = _('Registration')

    def refundLink(self, obj):
        change_url = reverse('refundProcessing', args=(obj.id, ))
        return mark_safe(
            '<a href="%s">%s</a>' % (change_url, gettext('Refund'))
        )
    refundLink.allow_tags = True
    refundLink.short_description = _('Refund')

    def links(self, obj):
        button_start = ''
        button_end = ''

        return mark_safe(
            button_start + '<br />'.join([
                self.viewInvoiceLink(obj) or '',
                self.notificationLink(obj) or '',
                self.refundLink(obj) or '',
                self.registrationLink(obj) or '',
            ]) + button_end
        )
    links.allow_tags = True
    links.short_description = _('Links')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.submissionUser = request.user
        super().save_model(request, obj, form, change)

    def get_fieldsets(self, request, obj=None):
        if not obj:
            return self.add_fieldsets
        else:
            return super().get_fieldsets(request, obj)
