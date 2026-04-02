from django.views.generic import CreateView
from django.utils.translation import gettext_lazy as _
from django.contrib.messages.views import SuccessMessageMixin

from braces.views import StaffuserRequiredMixin, UserFormKwargsMixin

from danceschool.core.mixins import AdminSuccessURLMixin

from ..forms import ExpenseReportingForm, RevenueReportingForm


class ExpenseReportingView(
    AdminSuccessURLMixin, StaffuserRequiredMixin, UserFormKwargsMixin,
    SuccessMessageMixin, CreateView
):
    template_name = 'cms/forms/display_crispy_form_classbased_admin.html'
    form_class = ExpenseReportingForm
    success_message = _('Expense item successfully submitted.')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'form_title': _('Report Expenses'),
            'form_description': _('Use this form to report expenses.'),
        })
        return context


class RevenueReportingView(
    AdminSuccessURLMixin, StaffuserRequiredMixin, UserFormKwargsMixin,
    SuccessMessageMixin, CreateView
):
    template_name = 'cms/forms/display_crispy_form_classbased_admin.html'
    form_class = RevenueReportingForm
    success_message = _('Revenue item successfully submitted.')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'form_title': _('Report Revenues'),
            'form_description': _('Use this form to report revenues.'),
        })
        return context
