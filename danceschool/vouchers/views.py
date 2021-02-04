from django.template import Template, Context
from django.views.generic import FormView
from django.test import RequestFactory
from django.utils.translation import gettext_lazy as _
from django.db import IntegrityError
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.urls import reverse

from easy_pdf.views import PDFTemplateView
import re
import logging
import random
import string
from braces.views import PermissionRequiredMixin

from danceschool.core.models import Invoice
from danceschool.core.constants import getConstant, PAYMENT_VALIDATION_STR
from danceschool.core.mixins import EmailRecipientMixin, SiteHistoryMixin
from danceschool.core.helpers import emailErrorMessage

from .forms import GiftCertificateCustomizationForm, VoucherGenerationForm
from .models import Voucher, VoucherCategory


# Define logger for this file
logger = logging.getLogger(__name__)


class GiftCertificateCustomizeView(FormView):
    template_name = 'cms/forms/display_form_classbased.html'
    form_class = GiftCertificateCustomizationForm

    def dispatch(self, request, *args, **kwargs):
        '''
        Check that a valid Invoice ID has been passed in session data,
        and that said invoice is marked as paid.
        '''
        paymentSession = request.session.get(PAYMENT_VALIDATION_STR, {})
        self.invoiceID = paymentSession.get('invoiceID')
        self.amount = paymentSession.get('amount', 0)
        self.success_url = paymentSession.get('success_url', reverse('registration'))

        # Check that Invoice matching passed ID exists
        try:
            i = Invoice.objects.get(id=self.invoiceID)
        except ObjectDoesNotExist:
            return HttpResponseBadRequest(_('Invalid invoice information passed.'))

        if i.unpaid or i.amountPaid != self.amount:
            return HttpResponseBadRequest(_('Passed invoice is not paid.'))

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        '''
        Create the gift certificate voucher with the indicated information and send
        the email as directed.
        '''
        emailTo = form.cleaned_data.get('emailTo')
        emailType = form.cleaned_data.get('emailType')
        recipientName = form.cleaned_data.get('recipientName')
        fromName = form.cleaned_data.get('fromName')
        message = form.cleaned_data.get('message')

        logger.info('Processing gift certificate.')

        try:
            voucher = Voucher.create_new_code(
                prefix='GC_',
                name=_(
                    'Gift certificate: %s%s for %s' % (
                        getConstant('general__currencySymbol'), self.amount, emailTo
                    )
                ),
                category=getConstant('vouchers__giftCertCategory'),
                originalAmount=self.amount,
                singleUse=False,
                forFirstTimeCustomersOnly=False,
                expirationDate=None,
            )
        except IntegrityError:
            logger.error('Error creating gift certificate voucher for Invoice #%s' % self.invoiceId)
            emailErrorMessage(_('Gift certificate transaction not completed'), self.invoiceId)

        template = getConstant('vouchers__giftCertTemplate')

        # Attempt to attach a PDF of the gift certificate
        rf = RequestFactory()
        pdf_request = rf.get('/')

        pdf_kwargs = {
            'currencySymbol': getConstant('general__currencySymbol'),
            'businessName': getConstant('contact__businessName'),
            'certificateAmount': voucher.originalAmount,
            'certificateCode': voucher.voucherId,
            'certificateMessage': message,
            'recipientName': recipientName,
            'fromName': fromName,
        }
        if recipientName:
            pdf_kwargs.update({})

        attachment = GiftCertificatePDFView(request=pdf_request).get(request=pdf_request, **pdf_kwargs).content or None

        if attachment:
            attachment_name = 'gift_certificate.pdf'
        else:
            attachment_name = None

        # Send a confirmation email
        email_class = EmailRecipientMixin()
        email_class.email_recipient(
            subject=template.subject,
            content=template.content,
            send_html=template.send_html,
            html_content=template.html_content,
            from_address=template.defaultFromAddress,
            from_name=template.defaultFromName,
            cc=template.defaultCC,
            to=emailTo,
            currencySymbol=getConstant('general__currencySymbol'),
            businessName=getConstant('contact__businessName'),
            certificateAmount=voucher.originalAmount,
            certificateCode=voucher.voucherId,
            certificateMessage=message,
            recipientName=recipientName,
            fromName=fromName,
            emailType=emailType,
            recipient_name=recipientName,
            attachment_name=attachment_name,
            attachment=attachment
        )

        # Remove the invoice session data
        self.request.session.pop(PAYMENT_VALIDATION_STR, None)

        return HttpResponseRedirect(self.get_success_url())


class GiftCertificatePDFView(PDFTemplateView):
    template_name = 'vouchers/pdf/giftcertificate_template.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        template = getConstant('vouchers__giftCertPDFTemplate')

        # For security reasons, the following tags are removed from the template before parsing:
        # {% extends %}{% load %}{% debug %}{% include %}{% ssi %}
        content = re.sub(r'\{%\s*((extends)|(load)|(debug)|(include)|(ssi))\s+.*?\s*%\}', '', template.content)

        t = Template(content)

        rendered_content = t.render(Context(context))

        context.update({
            'header': template.subject,
            'content': rendered_content
        })

        return context


class VoucherGenerationView(PermissionRequiredMixin, SiteHistoryMixin, FormView):
    ''' A simple view to rapidly generate and email vouchers. '''

    permission_required = 'vouchers.generate_and_email_vouchers'
    template_name = 'cms/forms/display_form_classbased.html'
    form_class = VoucherGenerationForm

    def get_initial(self):
        '''
        If request contains initial values for a prefix, an amount, or a category,
        then use it to populate the form.
        '''

        prefix_valid = re.compile(r'^[a-zA-Z\-_0-9]+$')
        prefix = (
            self.request.GET.get('prefix', '') if
            prefix_valid.match(self.request.GET.get('prefix', '')) else ''
        )

        name_valid = re.compile(r'^[a-zA-Z\-_0-9\+]+$')
        description = (
            self.request.GET.get('name', '').replace('-', ' ') if
            name_valid.match(self.request.GET.get('name', '')) else ''
        )

        new = False
        while not new:
            # Standard is a ten-letter random string of uppercase letters
            random_string = ''.join(random.choice(string.ascii_uppercase) for z in range(10))
            if not Voucher.objects.filter(voucherId='%s%s' % (prefix, random_string)).exists():
                new = True

        initial = {
            'voucherId': '%s%s' % (prefix, random_string),
            'description': description,
        }

        try:
            amount = float(self.request.GET.get('amount', ''))
            initial['amount'] = amount
        except ValueError:
            pass

        try:
            category = VoucherCategory.objects.get(id=self.request.GET.get('category', ''))
            initial['category'] = category
        except (ValueError, ObjectDoesNotExist):
            pass

        return initial

    def form_valid(self, form):

        voucherId = form.cleaned_data.get('voucherId')
        description = form.cleaned_data.get('description')
        amount = form.cleaned_data.get('amount')
        category = form.cleaned_data.get('category')

        emailTo = form.cleaned_data.get('emailTo')
        recipientName = form.cleaned_data.get('recipientName')

        logger.info('Processing voucher generation.')

        voucher = Voucher.objects.create(
            voucherId=voucherId, name=description, originalAmount=amount,
            category=category
        )

        if emailTo:
            template = getConstant('vouchers__autoGenerationTemplate')

            email_class = EmailRecipientMixin()
            email_class.email_recipient(
                subject=template.subject,
                content=template.content,
                send_html=template.send_html,
                html_content=template.html_content,
                from_address=template.defaultFromAddress,
                from_name=template.defaultFromName,
                cc=template.defaultCC,
                to=emailTo,
                currencySymbol=getConstant('general__currencySymbol'),
                businessName=getConstant('contact__businessName'),
                certificateAmount=voucher.originalAmount,
                certificateCode=voucher.voucherId,
                recipientName=recipientName,
                recipient_name=recipientName,
            )

        return HttpResponseRedirect(
            self.get_return_page().get('url') or reverse('registration')
        )
