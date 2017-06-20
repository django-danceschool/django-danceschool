from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

from cms.models.pluginmodel import CMSPlugin

from djangocms_text_ckeditor.fields import HTMLField
from datetime import datetime


@python_2_unicode_compatible
class NewsItem(models.Model):
    '''
    Each NewsItem will be posted on the news page, with the most recent news first.
    Alerts can be posted with special CSS to make them stand out.
    The most recent news item may be shown on the home page.
    '''

    title = models.CharField(max_length=200,help_text=_('Title the news item. Make sure this is descriptive.'))

    content = HTMLField(help_text=_('Insert news content here.'))

    alert = models.BooleanField(default=False, help_text=_('Alerts (such as cancellations) may be displayed in an emphasized fashion.'))

    pinThis = models.BooleanField(verbose_name=_('Pinned'), default=False, help_text=_('If this field is set, then the news item will continue to show up on the main page until someone unpins it.'))

    draft = models.BooleanField(default=False, help_text=_('Check to hide from publication'))
    hideThis = models.BooleanField(verbose_name=_('Hidden'), default=False, help_text=_('If for some reason you need to make a news item invisible, this will do that.'))

    creationDate = models.DateTimeField(auto_now_add=True)
    modifiedDate = models.DateTimeField(auto_now=True,help_text=_('Time of most recent edit'))
    publicationDate = models.DateTimeField(default=datetime.now)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ('-pinThis','-publicationDate',)


class LatestNewsPluginModel(CMSPlugin):
    maxItems = models.PositiveSmallIntegerField(verbose_name=_('Maximum number of items to show'),default=1)
    daysBefore = models.PositiveSmallIntegerField(verbose_name=_('Published since (days ago)'),help_text=_('Leave blank for no limit.'),null=True,blank=True)
    alertOnly = models.BooleanField(verbose_name=_('Show Alerts Only'),default=False)
    ignorePins = models.BooleanField(verbose_name=_('Ignore Pinned Item Precedence'),help_text=_('By default, pinned items are shown first, regardless of publication date. Checking this box overrides that behavior.'),default=False)
    template = models.CharField(max_length=250,null=True,blank=True)

    def get_short_description(self):
        desc = self.id
        choices = getattr(self.get_plugin_class(),'template_choices',[])
        choice_name = [x[1] for x in choices if x[0] == self.template]
        if choice_name:
            desc = choice_name[0]
        elif self.template:
            desc = self.template
        return desc
