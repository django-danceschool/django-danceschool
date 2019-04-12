from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar
from cms.toolbar.items import LinkItem
from cms.constants import RIGHT


@toolbar_pool.register
class NightlyDoorToolbar(CMSToolbar):
    ''' Adds links to Events for today's cash register '''

    def populate(self):
        if self.request.user.has_perm('core.accept_door_payments'):
            today = timezone.now()
            url=reverse('nightlyRegister', args=(today.year, today.month, today.day))

            self.toolbar.add_button(_('Door Register'), url=url, side=RIGHT)

            menu = self.toolbar.get_or_create_menu('core-events', _('Events'))
            position = menu.find_first(
                item_type=LinkItem, name=_('Registration Page')
            )

            menu.add_link_item(
                _('At-the-door Register'),
                url=url,
                position=position+1,
            )
