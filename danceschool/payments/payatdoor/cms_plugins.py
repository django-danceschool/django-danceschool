from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from django.utils.translation import ugettext_lazy as _
from django.conf import settings

from danceschool.core.constants import getConstant

from .models import PayAtDoorFormModel
from .forms import WillPayAtDoorForm, DoorPaymentForm


class PayAtDoorFormPlugin(CMSPluginBase):
    model = PayAtDoorFormModel
    name = _('At-the-door Payment Method')
    cache = False
    module = 'Payment'
    render_template = 'payatdoor/checkout.html'

    def render(self, context, instance, placeholder):
        ''' Add the cart-specific context to this form '''
        context = super(PayAtDoorFormPlugin, self).render(context, instance, placeholder)

        context.update({
            'business_name': getConstant('contact__businessName'),
            'currencyCode': getConstant('general__currencyCode'),
            'form': self.get_form(context, instance, placeholder),
        })

        return context

    def get_form(self, context, instance, placeholder):
        registration = getattr(context.get('registration', None),'id',None)
        invoice=getattr(context.get('invoice',None),'id',None)
        user=getattr(context.get('user',None),'id',None)
        payAtDoor = context.get('payAtDoor',None)

        if registration and payAtDoor is False:
            return WillPayAtDoorForm(user=user,invoice=invoice,registration=registration,instance=instance.id)
        elif invoice:
            return DoorPaymentForm(user=user,invoice=invoice,registration=registration,instance=instance.id)

plugin_pool.register_plugin(PayAtDoorFormPlugin)
