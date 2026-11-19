from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from danceschool.core.constants import getConstant

from .models import PayNowFormModel


class PaypalButtonPluginMixin:
    ''' Adds what the PayPal JavaScript SDK needs to load the button. '''

    def render(self, context, instance, placeholder):
        context = super().render(context, instance, placeholder)
        context.update({
            # The client ID is public; PayPal's JavaScript SDK requires it.
            'paypal_client_id': getattr(settings, 'PAYPAL_CLIENT_ID', ''),
            'currencyCode': getConstant('general__currencyCode'),
        })
        return context


class GiftCertificateFormPlugin(PaypalButtonPluginMixin, CMSPluginBase):
    model = PayNowFormModel
    name = _('Paypal Gift Certificate Form')
    render_template = "paypal/giftcertificate_form.html"
    cache = False
    module = 'Paypal'


class CartPaymentFormPlugin(PaypalButtonPluginMixin, CMSPluginBase):
    model = PayNowFormModel
    name = _('Paypal Express Checkout Form')
    render_template = "paypal/express_checkout.html"
    cache = False
    module = 'Paypal'


plugin_pool.register_plugin(GiftCertificateFormPlugin)
plugin_pool.register_plugin(CartPaymentFormPlugin)
