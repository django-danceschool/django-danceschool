from django.utils.translation import ugettext_lazy as _

from danceschool.core.registries import plugin_templates_registry, PluginTemplateBase


@plugin_templates_registry.register
class VoucherStatsTemplate(PluginTemplateBase):
    template_name = 'stats/schoolstats_voucherusage.html'
    plugin = 'StatsGraphPlugin'
    description = _('Statistics on Usage of Vouchers')
