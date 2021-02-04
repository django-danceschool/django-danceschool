from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from danceschool.core.models import CashPaymentRecord, Invoice
from danceschool.core.helpers import getReturnPage

from .forms import WillPayAtDoorForm, DoorPaymentForm

import logging


# Define logger for this file
logger = logging.getLogger(__name__)


class WillPayAtDoorView(FormView):
    form_class=WillPayAtDoorForm

    def post(self, request, *args, **kwargs):
        logger.info('Received request for at-the-door payment.')
        self.request = request
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        invoice = form.cleaned_data.get('invoice')
        instance = form.cleaned_data.get('instance')

        invoice.status = Invoice.PaymentStatus.unpaid
        invoice.save()

        if getattr(invoice, 'registration', None):
            invoice.registration.finalize()
        if instance:
            return HttpResponseRedirect(instance.successPage.get_absolute_url())

    def form_invalid(self, form):
        return HttpResponseBadRequest(str(form.errors))


class PayAtDoorView(FormView):
    form_class = DoorPaymentForm

    def post(self, request, *args, **kwargs):
        logger.info('Received request for at-the-door payment.')
        self.request = request
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        invoice = form.cleaned_data.get('invoice')
        amountPaid = form.cleaned_data.get('amountPaid')
        subUser = form.cleaned_data.get('submissionUser')
        paymentMethod = form.cleaned_data.get('paymentMethod')
        payerEmail = form.cleaned_data.get('payerEmail')
        receivedBy = form.cleaned_data.get('receivedBy')

        if not invoice:
            return HttpResponseBadRequest("No invoice")

        this_cash_payment = CashPaymentRecord.objects.create(
            invoice=invoice, amount=amountPaid,
            status=CashPaymentRecord.PaymentStatus.collected,
            paymentMethod=paymentMethod,
            payerEmail=payerEmail,
            submissionUser=subUser, collectedByUser=receivedBy,
        )
        invoice.processPayment(
            amount=amountPaid, fees=0, paidOnline=False, methodName=paymentMethod,
            submissionUser=subUser, collectedByUser=receivedBy,
            methodTxn='CASHPAYMENT_%s' % this_cash_payment.recordId,
            forceFinalize=True,
        )

        # Send users back to the invoice to confirm the successful payment.
        # If none is specified, then return to the registration page.
        returnPage = getReturnPage(self.request.session.get('SITE_HISTORY', {}))
        if returnPage.get('url'):
            return HttpResponseRedirect(returnPage['url'])
        return HttpResponseRedirect(reverse('registration'))

    def form_invalid(self, form):
        logger.error('Invalid request for at-the-door payment.')
        return HttpResponseBadRequest(str(form.errors))
