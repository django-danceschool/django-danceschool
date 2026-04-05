from django.http import HttpResponseRedirect, Http404, HttpResponseBadRequest
from django.template import Template, Context
from django.views.generic import FormView, DetailView
from django.contrib.auth.mixins import AccessMixin
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from braces.views import PermissionRequiredMixin, StaffuserRequiredMixin
from django_weasyprint import WeasyTemplateView
import re

from ..models import Invoice
from ..forms.invoice import InvoiceNotificationForm
from ..constants import getConstant
from ..mixins import FinancialContextMixin, AdminSuccessURLMixin, SiteHistoryMixin

import logging

logger = logging.getLogger(__name__)


################################################
# For Viewing Invoices and sending notifications


class ViewInvoiceView(AccessMixin, FinancialContextMixin, SiteHistoryMixin, DetailView):
    template_name = 'core/invoice.html'
    model = Invoice

    def get(self, request, *args, **kwargs):
        '''
        Invoices can be viewed only if the validation string is provided, unless
        the user is logged in and has view_all_invoice permissions
        '''
        self.object = self.get_object()
        user_has_permissions = request.user.has_perm('core.view_all_invoices')
        user_has_validation_string = (
            request.GET.get('v', None) == self.object.validationString
        )

        if user_has_validation_string or user_has_permissions:
            context = self.get_context_data(
                object=self.object,
                user_has_permissions=user_has_permissions,
                user_has_validation_string=user_has_validation_string
            )
            return self.render_to_response(context)
        return self.handle_no_permission()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'invoice': self.object,
            'payments': self.get_payments(),
        })

        # Update the session data so that subsequent views return to this page.
        self.set_return_page('viewInvoice', _('Invoice'), pk=str(self.object.pk))

        return context

    def get_payments(self):
        if not getattr(self, 'payments', None):
            self.payments = self.object.get_payments()
        return self.payments


class InvoiceNotificationView(FinancialContextMixin, AdminSuccessURLMixin,
                              PermissionRequiredMixin, StaffuserRequiredMixin, FormView):
    success_message = _('Invoice notifications successfully sent.')
    template_name = 'core/invoice_notification.html'
    permission_required = 'core.send_invoices'
    form_class = InvoiceNotificationForm

    def form_valid(self, form):
        invoice_ids = [
            k.replace('invoice_', '') for k, v in form.cleaned_data.items() if 'invoice_' in k and v is True
        ]
        invoices = [x for x in self.toNotify if str(x.id) in invoice_ids]

        for invoice in invoices:
            if invoice.get_default_recipients():
                invoice.sendNotification()

        messages.success(self.request, self.success_message)
        return HttpResponseRedirect(self.get_success_url())

    def dispatch(self, request, *args, **kwargs):
        ''' Get the set of invoices for which to permit notifications '''

        if 'pk' in self.kwargs:
            try:
                self.invoices = Invoice.objects.filter(pk=self.kwargs.get('pk'))[:]
            except ValueError:
                raise Http404()
            if not self.invoices:
                raise Http404()
        else:
            ids = request.GET.get('invoices', '')
            try:
                self.invoices = Invoice.objects.filter(id__in=[x for x in ids.split(', ')])[:]
            except ValueError:
                return HttpResponseBadRequest(_('Invalid invoice identifiers specified.'))

        if not self.invoices:
            return HttpResponseBadRequest(_('No invoice identifiers specified.'))

        toNotify = []
        cannotNotify = []

        for invoice in self.invoices:
            if invoice.get_default_recipients():
                toNotify.append(invoice)
            else:
                cannotNotify.append(invoice)
        self.toNotify = toNotify
        self.cannotNotify = cannotNotify

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        ''' Pass the set of invoices to the form for creation '''
        kwargs = super().get_form_kwargs()
        kwargs['invoices'] = self.toNotify
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'toNotify': self.toNotify,
            'cannotNotify': self.cannotNotify,
        })
        return context


class InvoicePDFView(PermissionRequiredMixin, FinancialContextMixin, WeasyTemplateView):
    template_name = 'core/pdf/invoice_pdf.html'
    pdf_filename = 'invoice.pdf'
    permission_required = 'core.view_all_invoices'

    def get(self, request, *args, **kwargs):
        '''
        Ensure that the invoice is loaded
        '''
        pk = self.kwargs.get('pk')
        self.object = Invoice.objects.filter(pk=pk).first()
        if not self.object:
            return self.handle_no_permission()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'object': self.object,
            'invoice': self.object,
            'payments': self.get_payments(),
        })

        template = getConstant('registration__invoicePDFTemplate')

        # For security reasons, the following tags are removed from the template before parsing:
        # {% extends %}{% load %}{% debug %}{% include %}{% ssi %}
        content = re.sub(r'\{%\s*((extends)|(load)|(debug)|(include)|(ssi))\s+.*?\s*%\}', '', template.content)

        t = Template(content)

        rendered_content = t.render(Context(context))

        context.update({
            'payment_instructions': rendered_content
        })

        return context

    def get_payments(self):
        if not getattr(self, 'payments', None):
            self.payments = self.object.get_payments()
        return self.payments
