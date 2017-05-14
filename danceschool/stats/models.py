from django.db import models
from django.utils.translation import ugettext_lazy as _

from cms.models.pluginmodel import CMSPlugin


class StatsGraphPluginModel(CMSPlugin):
    '''
    A model for showing different types of school stats.  In general, the templates for these
    plugin instances call the specific URLs that they require to pull the data for the graph,
    so this model allows for only a template to be specified.
    '''
    template = models.CharField(verbose_name=_('Template'),max_length=250,null=True,blank=True)
