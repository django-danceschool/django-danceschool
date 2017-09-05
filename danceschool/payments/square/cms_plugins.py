from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from django.utils.translation import ugettext_lazy as _
from django.conf import settings


from .models import SquareCheckoutFormModel


class SquareCheckoutFormPlugin(CMSPluginBase):
    model = SquareCheckoutFormModel
    name = _('Square Checkout Form')
    render_template = "square/checkout.html"
    cache = False
    module = 'Square'

    def render(self, context, instance, placeholder):
        ''' Add the cart-specific context to this form '''
        context = super(SquareCheckoutFormPlugin, self).render(context, instance, placeholder)

        context.update({
            'squareApplicationId': getattr(settings,'SQUARE_APPLICATION_ID',''),
        })

        return context


plugin_pool.register_plugin(SquareCheckoutFormPlugin)
