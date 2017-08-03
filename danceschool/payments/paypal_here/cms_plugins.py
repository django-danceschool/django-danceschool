from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from cms.models.pluginmodel import CMSPlugin

from django.utils.translation import ugettext_lazy as _


class PaypalHereFormPlugin(CMSPluginBase):
    model = CMSPlugin
    name = _('Paypal Here Integration Form')
    render_template = "paypal_here/paypal_here_checkout.html"
    cache = False
    module = 'Paypal'


plugin_pool.register_plugin(PaypalHereFormPlugin)
