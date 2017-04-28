from django.test import RequestFactory
from django.utils.translation import ugettext_lazy as _

from danceschool.core.helpers import emailErrorMessage
from danceschool.core.emails import renderEmail
from danceschool.core.models import EmailTemplate
from danceschool.core.constants import getConstant

import logging

from .models import Voucher, VoucherCategory
from .views import GiftCertificatePDFView


# Define logger for this file
logger = logging.getLogger(__name__)


def processGiftCertificate(mc_gross,payer_email,payment_status,txn_id,recipient_name=''):
    '''
    If a gift certificate has been purchased and the amount
    has been received, this function creates a Voucher for
    that gift certificate with a unique code, and then requests
    that a confirmation email be sent to the person who purchased
    the certificate.
    '''
    logger.info('Processing gift certificate.')

    if payment_status != 'Completed':
        logger.warning('Error: Payment status is not Completed, gift certificate not processed.')
        emailErrorMessage(_('Gift certificate transaction not completed'),txn_id)
        return
    try:
        voucher = Voucher.objects.create(
            voucherId='GC_' + str(txn_id),
            name=_('Gift certificate: %s%s for %s' % (getConstant('general__currencySymbol'),mc_gross, payer_email)),
            category=VoucherCategory.objects.get(id=getConstant('vouchers__giftCertCategoryID')),
            originalAmount=mc_gross,
            singleUse=False,
            forFirstTimeCustomersOnly=False,
            expirationDate=None,
        )
    except:
        emailErrorMessage(_('Gift certificate transaction not completed'),txn_id)

    template = EmailTemplate.objects.get(id=getConstant('vouchers__giftCertTemplateID'))

    # Attempt to attach a PDF of the gift certificate
    rf = RequestFactory()
    request = rf.get('/')

    pdf_kwargs = {
        'certificateAmount': voucher.originalAmount,
        'certificateCode': voucher.voucherId,
    }
    if recipient_name:
        pdf_kwargs.update({'recipientName': recipient_name})

    attachment = GiftCertificatePDFView(request=request).get(request=request,**pdf_kwargs).content or None

    if attachment:
        attachment_name = 'gift_certificate.pdf'
    else:
        attachment_name = None

    # Send a confirmation email
    renderEmail(
        subject=template.subject,
        content=template.content,
        from_address=template.defaultFromAddress,
        from_name=template.defaultFromName,
        cc=template.defaultCC,
        to=payer_email,
        certificateAmount=voucher.originalAmount,
        certificateCode=voucher.voucherId,
        recipient_name=recipient_name,
        attachment_name=attachment_name,
        attachment=attachment
    )
