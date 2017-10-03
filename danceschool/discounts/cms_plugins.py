from django.utils.translation import ugettext_lazy as _

from danceschool.core.registries import plugin_templates_registry, PluginTemplateBase


@plugin_templates_registry.register
class DiscountStatsTemplate(PluginTemplateBase):
    template_name = 'stats/schoolstats_discountusage.html'
    plugin = 'StatsGraphPlugin'
    description = _('Statistics on Usage of Discounts')
