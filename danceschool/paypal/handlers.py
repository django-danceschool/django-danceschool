from django.dispatch import receiver
from django.core.exceptions import ObjectDoesNotExist

import logging

from danceschool.core.signals import get_invoice_payments, refund_invoice_payment

from .models import PaymentRecord

# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(get_invoice_payments)
def getPaypalPayments(sender,**kwargs):
    invoice = kwargs.get('invoice',None)
    if not invoice:
        return

    paypal_payments = PaymentRecord.objects.filter(invoice=invoice)
    if paypal_payments.count() == 0:
        return

    return [{
        'method': 'Paypal Express Checkout',
        'id': x.paymentId,
        'netAmountPaid': x.getNetAmountPaid(),
    } for x in paypal_payments]


@receiver(refund_invoice_payment)
def refundPaypalPayment(sender,**kwargs):

    method = kwargs.get('method')
    id = kwargs.get('id')
    refundAmount = kwargs.get('refundAmount',None)

    if method != 'Paypal Express Checkout':
        return

    try:
        this_payment = PaymentRecord.objects.get(paymentId=id)
    except ObjectDoesNotExist:
        return {'status': 'error', 'errorMessage': 'No payment record found.'}

    return this_payment.refund(amount=refundAmount)
