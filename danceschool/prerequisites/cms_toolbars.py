from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar


@toolbar_pool.register
class RequirementLinksToolbar(CMSToolbar):
    ''' Add link to Requirements admin to the Events Related Items '''

    def populate(self):
        if not self.request.user.has_perm('prerequisites.change_requirement'):
            return

        menu = self.toolbar.get_or_create_menu('core-events', _('Events'))
        related_menu = menu.get_or_create_menu('core-events-related',_('Related Items'))
        related_menu.add_link_item(_('Registration Requirements/Prerequisites'), url=reverse('admin:prerequisites_requirement_changelist'))
