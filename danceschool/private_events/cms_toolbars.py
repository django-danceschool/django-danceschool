from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar
from cms.toolbar.items import BaseItem


@toolbar_pool.register
class PrivateEventsToolbar(CMSToolbar):
    ''' Adds private events links to the Staff toolbar and category links to the related items toolbar '''

    def populate(self):
        staff_menu = self.toolbar.get_or_create_menu('core-staffmember',_('Staff'))

        if hasattr(self.request.user,'staffmember') and self.request.user.staffmember.feedKey:
            position = staff_menu.find_first(BaseItem,name=_('Your Stats')) or 0
            staff_menu.add_link_item(_('Your Private Calendar'), url=reverse('privateCalendar'), position=position + 1)

        if self.request.user.has_perm('private_events.change_privateeventcategory'):
            events_menu = self.toolbar.get_or_create_menu('core-events',_('Events'))
            related_menu = events_menu.get_or_create_menu('core-events-related',_('Related Items'))

            related_menu.add_link_item(_('Private Event Categories'),url=reverse('admin:private_events_privateeventcategory_changelist'))
