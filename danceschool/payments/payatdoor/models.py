from django.db import models
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from cms.models.pluginmodel import CMSPlugin
from cms.models.fields import PageField

import logging

# Define logger for this file
logger = logging.getLogger(__name__)


class PayAtDoorFormModel(CMSPlugin):
    ''' This model holds options for instances of the PayAtDoorFormPlugin '''

    successPage = PageField(verbose_name=_('Success Page'),help_text=_('When the user returns to the site after a successful transaction, send them to this page.'),related_name='successPageForPayAtDoor')

    def get_short_description(self):
        return self.plugin_type or self.id
