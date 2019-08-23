from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from cms.models.pluginmodel import CMSPlugin
from django.utils.translation import ugettext_lazy as _
from django.conf import settings

from danceschool.core.constants import getConstant

from .models import PayAtDoorFormModel
from .forms import WillPayAtDoorForm, DoorPaymentForm


class WillPayAtDoorFormPlugin(CMSPluginBase):
    model = PayAtDoorFormModel
    name = _('Agreement to pay at-the-door')
    module = _('Payments')
    cache = False
    render_template = 'cms/forms/plugin_crispy_form.html'

    def render(self, context, instance, placeholder):
        ''' Add the cart-specific context to this form '''
        context = super().render(context, instance, placeholder)

        context.update({
            'business_name': getConstant('contact__businessName'),
            'currencyCode': getConstant('general__currencyCode'),
            'form': self.get_cart_form(context, instance, placeholder),
        })

        return context

    def get_cart_form(self, context, instance, *args, **kwargs):
        registration = getattr(context.get('registration', None), 'id', None)
        invoice = getattr(context.get('invoice', None), 'id', None)
        user = getattr(context.get('user', None), 'id', None)

        return WillPayAtDoorForm(
            user=user, invoice=invoice, registration=registration, instance=instance.id
        )


class PayAtDoorFormPlugin(CMSPluginBase):
    model = CMSPlugin
    name = _('At-the-door payment form')
    module = _('Payments')
    cache = False
    render_template = 'cms/forms/plugin_crispy_form.html'

    def render(self, context, instance, placeholder):
        ''' Add the cart-specific context to this form '''
        context = super().render(context, instance, placeholder)

        context.update({
            'business_name': getConstant('contact__businessName'),
            'currencyCode': getConstant('general__currencyCode'),
            'form': self.get_cart_form(context, instance, placeholder),
        })

        return context

    def get_cart_form(self, context, instance, *args, **kwargs):
        registration = getattr(context.get('registration', None), 'id', '')
        invoice = str(getattr(context.get('invoice', None), 'id', ''))
        user = getattr(context.get('user', None), 'id', '')

        return DoorPaymentForm(
            user=user, invoice=invoice, registration=registration
        )


plugin_pool.register_plugin(WillPayAtDoorFormPlugin)
plugin_pool.register_plugin(PayAtDoorFormPlugin)
