from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from dateutil.relativedelta import relativedelta

from danceschool.core.models import Series
from danceschool.core.mixins import PluginTemplateMixin

from .models import StatsGraphPluginModel


class StatsGraphPlugin(PluginTemplateMixin, CMSPluginBase):
    model = StatsGraphPluginModel
    name = _('School Performance Graph')
    render_template = 'stats/schoolstats_timeseriesbymonth.html'
    admin_preview = True

    template_choices = [
        ('stats/schoolstats_timeseriesbymonth.html',_('Students By Month of the Year')),
        ('stats/schoolstats_averagebyclasstype.html',_('Performance By Class Type')),
        ('stats/schoolstats_averagebyclasstypemonth.html',_('Performance By Class Type and Month of the Year')),
        ('stats/schoolstats_cohortretention.html',_('Number of Classes Taken By Starting Cohort')),
        ('stats/schoolstats_averagesbylocation.html',_('Performance By Location')),
        ('stats/schoolstats_registrationtypes.html',_('Student Discounts and At-The-Door Registrations')),
        ('stats/schoolstats_referralcounts.html',_('Tracked Advertising Referrals')),
    ]

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
