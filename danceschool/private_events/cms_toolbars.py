from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar
from cms.toolbar.items import Break


@toolbar_pool.register
class PrivateEventsToolbar(CMSToolbar):
    ''' Adds private events links to the Staff toolbar and category links to the related items toolbar '''

    def populate(self):
        events_menu = self.toolbar.get_or_create_menu('core-events',_('Events'))

        # Place the "School Calendar" link after the Registration Page link, before the break
        position = events_menu.find_first(Break,identifier='post_registration_break') or 0
        events_menu.add_link_item(_('School Calendar'), url=reverse('privateCalendar'), position=position)

        if self.request.user.has_perm('private_events.change_privateeventcategory'):
            related_menu = events_menu.get_or_create_menu('core-events-related',_('Related Items'))
            related_menu.add_link_item(_('Private Event Categories'),url=reverse('admin:private_events_privateeventcategory_changelist'))
