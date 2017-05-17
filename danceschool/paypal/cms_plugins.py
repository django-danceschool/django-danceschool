from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from django.utils.translation import ugettext_lazy as _
from django.conf import settings

from uuid import uuid4

from danceschool.vouchers.models import Voucher

from .models import PayNowFormModel, IPNMessage


class GiftCertificateFormPlugin(CMSPluginBase):
    model = PayNowFormModel
    name = _('Paypal Gift Certificate Form')
    render_template = "paypal/giftcertificate_form.html"
    cache = False
    module = 'Paypal'

    def render(self, context, instance, placeholder):
        ''' Create a UUID and check if a voucher with that ID exists before rendering '''
        context = super(GiftCertificateFormPlugin, self).render(context, instance, placeholder)

        invoice_id = str(uuid4())
        while IPNMessage.objects.filter(txn_id=invoice_id).count() > 0 or Voucher.objects.filter(voucherId='GC_%s' % invoice_id).count() > 0:
            invoice_id = str(uuid4())

        context.update({
            'invoice_id': invoice_id,
            'paypal_url': getattr(settings,'PAYPAL_URL',''),
            'paypal_account': getattr(settings,'PAYPAL_ACCOUNT',''),
        })

        return context


class CartPaymentFormPlugin(CMSPluginBase):
    model = PayNowFormModel
    name = _('Paypal Pay Now Form')
    render_template = "paypal/paynow_form.html"
    cache = False
    module = 'Paypal'

    def render(self, context, instance, placeholder):
        ''' Add the cart-specific context to this form '''
        context = super(CartPaymentFormPlugin, self).render(context, instance, placeholder)

        context.update({
            'paypal_url': getattr(settings,'PAYPAL_URL',''),
            'paypal_account': getattr(settings,'PAYPAL_ACCOUNT',''),
        })

        return context


plugin_pool.register_plugin(GiftCertificateFormPlugin)
plugin_pool.register_plugin(CartPaymentFormPlugin)
