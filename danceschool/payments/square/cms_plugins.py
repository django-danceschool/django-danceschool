from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.urls import reverse

from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
import uuid

from .models import SquareCheckoutFormModel


class SquareCheckoutFormPlugin(CMSPluginBase):
    model = SquareCheckoutFormModel
    name = _('Square Checkout Form')
    render_template = "square/checkout.html"
    cache = False
    module = 'Square'

    def render(self, context, instance, placeholder):
        ''' Add the cart-specific context to this form '''
        context = super().render(context, instance, placeholder)

        context.update({
            'allow_amount_entry': False,
            'squareApplicationId': getattr(settings, 'SQUARE_APPLICATION_ID', ''),
            'idempotency_key': str(uuid.uuid1()),
        })

        return context


class SquareGiftCertificateFormPlugin(SquareCheckoutFormPlugin):
    name = _('Square Gift Certificate Form')

    def render(self, context, instance, placeholder):
        context = super().render(context, instance, placeholder)

        context.update({
            'allow_amount_entry': True,
            'transaction_type': 'Gift Certificate',
        })

        return context


class SquarePointOfSalePlugin(CMSPluginBase):
    model = SquareCheckoutFormModel
    name = _('Square Point of Sale Button')
    render_template = "square/point_of_sale.html"
    cache = False
    module = 'Square'

    def render(self, context, instance, placeholder):
        context = super().render(context, instance, placeholder)

        context.update({
            'squareApplicationId': getattr(settings, 'SQUARE_APPLICATION_ID', ''),
            'returnUrl': context['request'].build_absolute_uri(reverse('processSquarePointOfSale')),
        })

        return context


plugin_pool.register_plugin(SquareCheckoutFormPlugin)
plugin_pool.register_plugin(SquareGiftCertificateFormPlugin)
plugin_pool.register_plugin(SquarePointOfSalePlugin)
