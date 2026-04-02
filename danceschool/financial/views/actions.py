from django.views.generic import FormView
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.utils.translation import gettext_lazy as _, gettext
from django.utils import timezone
from django.contrib.messages.views import SuccessMessageMixin
from django.forms.models import model_to_dict

from collections import OrderedDict

from braces.views import PermissionRequiredMixin

from danceschool.core.models import StaffMember, EventStaffCategory
from danceschool.core.mixins import AdminSuccessURLMixin, FinancialContextMixin
from danceschool.core.utils.requests import getIntFromGet

from ..models import ExpenseItem, RepeatedExpenseRule, StaffMemberWageInfo
from ..helpers.expenses import (
    createExpenseItemsForEvents, createExpenseItemsForVenueRental,
    createGenericExpenseItems,
)
from ..helpers.revenues import createRevenueItemsForRegistrations
from ..forms import (
    CompensationRuleUpdateForm, CompensationRuleResetForm, ExpenseRuleGenerationForm,
    ExpenseDuplicationForm, ExpenseDuplicationFormset,
)


class ExpenseDuplicationView(
    SuccessMessageMixin, AdminSuccessURLMixin, PermissionRequiredMixin,
    FinancialContextMixin, FormView
):
    '''
    Base class with repeated logic for update and replace actions.
    '''
    permission_required = 'financial.add_expenseitem'
    objectClass = ExpenseItem
    form_class = ExpenseDuplicationForm
    template_name = 'financial/duplicate_expenses.html'

    def dispatch(self, request, *args, **kwargs):
        ids = request.GET.get('ids')

        try:
            self.queryset = self.objectClass.objects.filter(id__in=[int(x) for x in ids.split(', ')])
        except ValueError:
            return HttpResponseBadRequest(_('Invalid ids passed'))

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.queryset

        if self.request.POST:
            context['itemDuplicates'] = ExpenseDuplicationFormset(
                self.request.POST, prefix='itemDuplicates'
            )
        else:
            context['itemDuplicates'] = ExpenseDuplicationFormset(
                prefix='itemDuplicates'
            )

        return context

    def form_valid(self, form):
        context = self.get_context_data()

        items = context.get('items')
        itemDuplicates = context.get('itemDuplicates')

        if itemDuplicates.is_valid():
            for old_item in items:
                for dup in itemDuplicates:

                    # Reset the key to reset the item.
                    new_item = old_item
                    new_item.pk = None

                    new_item.approvalDate = None
                    new_item.approved = dup.cleaned_data.get('approved')

                    new_item.paid = dup.cleaned_data.get('paid')

                    if new_item.paid:
                        new_item.paymentDate = dup.cleaned_data.get(
                            'paymentDate', timezone.now()
                        )
                    else:
                        new_item.paymentDate = None

                    if not new_item.event:
                        new_item.accrualDate = new_item.paymentDate or timezone.now()

                    if dup.cleaned_data.get('total') is not None:
                        new_item.total = dup.cleaned_data.get('total')

                    new_item.adjustments = 0
                    new_item.fees = 0

                    for k in ['periodStart', 'periodEnd', 'expenseRule']:
                        setattr(new_item, k, None)

                    new_item.submissionUser = getattr(self.request, 'user', None)

                    new_item.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('admin:financial_expenseitem_changelist')


class CompensationActionView(
    SuccessMessageMixin, AdminSuccessURLMixin, PermissionRequiredMixin,
    FinancialContextMixin, FormView
):
    '''
    Base class with repeated logic for update and replace actions.
    '''
    permission_required = 'core.change_staffmember'

    def dispatch(self, request, *args, **kwargs):
        ids = request.GET.get('ids')
        ct = getIntFromGet(request, 'ct')

        try:
            contentType = ContentType.objects.get(id=ct)
            self.objectClass = contentType.model_class()
        except (ValueError, ObjectDoesNotExist):
            return HttpResponseBadRequest(_('Invalid content type passed.'))

        # This view only deals with StaffMember
        if not isinstance(self.objectClass(), StaffMember):
            return HttpResponseBadRequest(_('Invalid content type passed.'))

        try:
            self.queryset = self.objectClass.objects.filter(id__in=[int(x) for x in ids.split(', ')])
        except ValueError:
            return HttpResponseBadRequest(_('Invalid ids passed'))

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self, **kwargs):
        ''' pass the list of staff members along to the form '''
        kwargs = super().get_form_kwargs(**kwargs)
        kwargs['staffmembers'] = self.queryset
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'staffmembers': self.queryset,
            'rateRuleValues': dict(RepeatedExpenseRule.RateRuleChoices.choices),
        })

        return context


class CompensationRuleUpdateView(CompensationActionView):
    '''
    This view is for an admin action to bulk update staff member compensation information.
    '''
    template_name = 'financial/update_staff_compensation_rules.html'
    form_class = CompensationRuleUpdateForm
    success_message = _('Staff member compensation rules updated successfully.')

    def form_valid(self, form):
        category = form.cleaned_data.pop('category', None)

        for staffmember in self.queryset:
            staffmember.expenserules.update_or_create(
                category=category,
                defaults=form.cleaned_data,
            )

        return super().form_valid(form)


class CompensationRuleResetView(CompensationActionView):
    '''
    This view is for an admin action to bulk delete custom staff member compensation information
    and/or reset to category defaults.
    '''
    template_name = 'financial/reset_staff_compensation_rules.html'
    form_class = CompensationRuleResetForm
    success_message = _('Staff member compensation rules reset successfully.')

    def form_valid(self, form):
        resetHow = form.cleaned_data.get('resetHow')

        cat_numbers = [
            int(x.split('_')[1]) for x in [
                y[0] for y in form.cleaned_data.items() if y[1] and 'category_' in y[0]
            ]
        ]

        if resetHow == 'DELETE':
            StaffMemberWageInfo.objects.filter(staffMember__in=self.queryset, category__in=cat_numbers).delete()
        elif resetHow == 'COPY':
            cats = EventStaffCategory.objects.filter(id__in=cat_numbers, defaultwage__isnull=False)
            for this_cat in cats:
                this_default = model_to_dict(
                    this_cat.defaultwage,
                    exclude=('category', 'id', 'repeatedexpenserule_ptr', 'lastRun')
                )

                for staffmember in self.queryset:
                    staffmember.expenserules.update_or_create(
                        category=this_cat,
                        defaults=this_default,
                    )

        return super().form_valid(form)


class ExpenseRuleGenerationView(AdminSuccessURLMixin, PermissionRequiredMixin, FormView):
    template_name = 'financial/expense_generation.html'
    form_class = ExpenseRuleGenerationForm
    permission_required = 'financial.can_generate_repeated_expenses'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        fields = getattr(context.get('form', {}), 'fields', OrderedDict())

        context.update({
            'form_title': _('Generate rule-based financial items'),
            'form_description': _(
                'This form is used to generate expense items and revenue items ' +
                'based on pre-set repeated expense rules. Please check the boxes ' +
                'for the rules that you wish to apply. Depending on your site ' +
                'settings, regular automatic generation of these financial items ' +
                'may already be occurring. Using this form should not lead duplicate ' +
                'items to be generated under these rules.'
            ),
            'staff_keys': [
                key for key in fields.keys()
                if key.startswith('staff') and key != 'staff'
            ],
            'venue_keys': [
                key for key in fields.keys()
                if key.startswith('location') or key.startswith('room')
            ],
            'generic_keys': [
                key for key in fields.keys()
                if key.startswith('generic') and key != 'generic'
            ],
        })
        return context

    def form_valid(self, form):
        try:
            generic_rules = RepeatedExpenseRule.objects.filter(id__in=[
                int(key.split('_')[-1]) for key, value in form.cleaned_data.items() if key.startswith('rule_') and value
            ]).order_by('id')
            location_rules = RepeatedExpenseRule.objects.filter(id__in=[
                int(key.split('_')[-1]) for key, value in form.cleaned_data.items() if (
                    key.startswith('locationrule_') or key.startswith('roomrule_')
                ) and value
            ]).order_by('id')
            staff_rules = RepeatedExpenseRule.objects.filter(id__in=[
                int(key.split('_')[-1]) for key, value in form.cleaned_data.items() if (
                    key.startswith('staffdefaultrule_') or key.startswith('staffmemberrule_')
                ) and value
            ]).order_by('id')
        except ValueError:
            return HttpResponseBadRequest(_('Invalid rules provided.'))

        response_items = [
            {
                'name': x.ruleName,
                'id': x.id,
                'type': _('Venue rental'),
                'created': createExpenseItemsForVenueRental(rule=x)
            } for x in location_rules
        ]
        response_items += [
            {
                'name': x.ruleName,
                'id': x.id,
                'type': _('Staff expenses'),
                'created': createExpenseItemsForEvents(rule=x)
            } for x in staff_rules
        ]
        response_items += [
            {
                'name': x.ruleName,
                'id': x.id,
                'type': _('Other expenses'),
                'created': createGenericExpenseItems(rule=x)
            } for x in generic_rules
        ]
        if form.cleaned_data.get('registrations'):
            response_items += [{
                'name': _('Revenue items for registrations'),
                'type': _('Revenue items for registrations'),
                'created': createRevenueItemsForRegistrations()
            }, ]

        success_message = gettext(
            'Successfully created {count} financial items.'.format(
                count=sum([x.get('created', 0) or 0 for x in response_items])
            )
        )
        messages.success(self.request, success_message)
        return HttpResponseRedirect(self.get_success_url())
