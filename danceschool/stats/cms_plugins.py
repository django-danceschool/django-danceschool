from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from dateutil.relativedelta import relativedelta

from danceschool.core.models import Series
from danceschool.core.mixins import PluginTemplateMixin
from danceschool.core.registries import plugin_templates_registry, PluginTemplateBase

from .models import StatsGraphPluginModel


class StatsGraphPlugin(PluginTemplateMixin, CMSPluginBase):
    model = StatsGraphPluginModel
    name = _('School Performance Graph')
    render_template = 'stats/schoolstats_timeseriesbymonth.html'
    admin_preview = True
    cache = True
    module = _('Stats')

    def render(self, context, instance, placeholder):
        ''' Allows this plugin to use templates designed for a list of locations. '''
        context = super(StatsGraphPlugin,self).render(context,instance,placeholder)

        # Javascript makes it difficult to calculate date/time differences, so instead
        # pass the most useful ones to the template context in a dictionary.  These are used
        # to show stats over different time ranges.
        limitMonthDates = {}
        for m in range(0,25):
            limitMonthDates[m] = (timezone.now() - relativedelta(months=m)).strftime('%Y-%m-%d')

        # The same for graphs that allow one to choose different years.
        recentYears = [timezone.now().year + x for x in range(-5,1)]

        series_by_year = Series.objects.order_by('year')

        if series_by_year.count() > 0:
            first_year = series_by_year.first().year
            allYears = [x for x in range(first_year,timezone.now().year + 1)]
        else:
            allYears = []

        context.update({
            'limitMonthDates': limitMonthDates,
            'recentYears': recentYears,
            'allYears': allYears,
        })
        return context


plugin_pool.register_plugin(StatsGraphPlugin)


@plugin_templates_registry.register
class StudentByMonthTemplate(PluginTemplateBase):
    template_name = 'stats/schoolstats_timeseriesbymonth.html'
    plugin = 'StatsGraphPlugin'
    description = _('Students By Month of the Year')


@plugin_templates_registry.register
class AvgByClassTypeTemplate(PluginTemplateBase):
    template_name = 'stats/schoolstats_averagebyclasstype.html'
    plugin = 'StatsGraphPlugin'
    description = _('Performance By Class Type')


@plugin_templates_registry.register
class AvgByClassTypeMonthTemplate(PluginTemplateBase):
    template_name = 'stats/schoolstats_averagebyclasstypemonth.html'
    plugin = 'StatsGraphPlugin'
    description = _('Performance By Class Type and Month of the Year')


@plugin_templates_registry.register
class CohortRetentionTemplate(PluginTemplateBase):
    template_name = 'stats/schoolstats_cohortretention.html'
    plugin = 'StatsGraphPlugin'
    description = _('Number of Classes Taken By Starting Cohort')


@plugin_templates_registry.register
class AvgByLocationTemplate(PluginTemplateBase):
    template_name = 'stats/schoolstats_averagesbylocation.html'
    plugin = 'StatsGraphPlugin'
    description = _('Performance By Location')


@plugin_templates_registry.register
class AdvanceRegistrationTemplate(PluginTemplateBase):
    template_name = 'stats/schoolstats_advanceregistration.html'
    plugin = 'StatsGraphPlugin'
    description = _('Advance Registration Time')


@plugin_templates_registry.register
class MultiClassRegistrationTemplate(PluginTemplateBase):
    template_name = 'stats/schoolstats_multiregistrations.html'
    plugin = 'StatsGraphPlugin'
    description = _('Multi-Series Registration Stats')


@plugin_templates_registry.register
class RegistrationTypesTemplate(PluginTemplateBase):
    template_name = 'stats/schoolstats_registrationtypes.html'
    plugin = 'StatsGraphPlugin'
    description = _('Student Discounts and At-The-Door Registrations')


@plugin_templates_registry.register
class ReferralCountsTemplate(PluginTemplateBase):
    template_name = 'stats/schoolstats_referralcounts.html'
    plugin = 'StatsGraphPlugin'
    description = _('Tracked Advertising Referrals')


@plugin_templates_registry.register
class BestCustomersTemplate(PluginTemplateBase):
    template_name = 'stats/schoolstats_bestcustomers.html'
    plugin = 'StatsGraphPlugin'
    description = _('Best Customers and Most Active Teachers')
