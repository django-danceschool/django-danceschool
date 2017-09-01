from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from django.utils.translation import ugettext_lazy as _
from django.conf import settings

from danceschool.core.constants import getConstant

from .models import StripeChargeFormModel


class StripeGiftCertificateFormPlugin(CMSPluginBase):
    model = StripeChargeFormModel
    name = _('Stripe Gift Certificate Form')
    render_template = "stripe/giftcertificate_form.html"
    cache = False
    module = 'Stripe'

    def render(self, context, instance, placeholder):
        ''' Create a UUID and check if a voucher with that ID exists before rendering '''
        context = super(StripeGiftCertificateFormPlugin, self).render(context, instance, placeholder)

        context.update({
            'stripe_key': getattr(settings,'STRIPE_PUBLIC_KEY',''),
            'business_name': getConstant('contact__businessName'),
            'currencyCode': getConstant('general__currencyCode'),
        })

        return context


class StripePaymentFormPlugin(CMSPluginBase):
    model = StripeChargeFormModel
    name = _('Stripe Checkout Form')
    render_template = "stripe/checkout.html"
    cache = False
    module = 'Stripe'

    def render(self, context, instance, placeholder):
        ''' Add the cart-specific context to this form '''
        context = super(StripePaymentFormPlugin, self).render(context, instance, placeholder)

        context.update({
            'stripe_key': getattr(settings,'STRIPE_PUBLIC_KEY',''),
            'business_name': getConstant('contact__businessName'),
            'currencyCode': getConstant('general__currencyCode'),
        })

        return context


plugin_pool.register_plugin(StripeGiftCertificateFormPlugin)
plugin_pool.register_plugin(StripePaymentFormPlugin)
