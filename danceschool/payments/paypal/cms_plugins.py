from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from django.utils.translation import ugettext_lazy as _
from django.conf import settings


from .models import PayNowFormModel


class GiftCertificateFormPlugin(CMSPluginBase):
    model = PayNowFormModel
    name = _('Paypal Gift Certificate Form')
    render_template = "paypal/giftcertificate_form.html"
    cache = False
    module = 'Paypal'

    def render(self, context, instance, placeholder):
        ''' Create a UUID and check if a voucher with that ID exists before rendering '''
        context = super(GiftCertificateFormPlugin, self).render(context, instance, placeholder)

        # Paypal "live" mode is "production" to checkout.js
        mode = getattr(settings,'PAYPAL_MODE', 'sandbox')
        if mode == 'live':
            mode = 'production'

        context.update({
            'paypal_mode': mode,
        })

        return context


class CartPaymentFormPlugin(CMSPluginBase):
    model = PayNowFormModel
    name = _('Paypal Express Checkout Form')
    render_template = "paypal/express_checkout.html"
    cache = False
    module = 'Paypal'

    def render(self, context, instance, placeholder):
        ''' Add the cart-specific context to this form '''
        context = super(CartPaymentFormPlugin, self).render(context, instance, placeholder)

        # Paypal "live" mode is "production" to checkout.js
        mode = getattr(settings,'PAYPAL_MODE', 'sandbox')
        if mode == 'live':
            mode = 'production'

        context.update({
            'paypal_mode': mode,
        })

        return context


plugin_pool.register_plugin(GiftCertificateFormPlugin)
plugin_pool.register_plugin(CartPaymentFormPlugin)
