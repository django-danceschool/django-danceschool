from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from django.urls.exceptions import NoReverseMatch

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar
from cms.toolbar.items import SubMenu


@toolbar_pool.register
class StatsToolbar(CMSToolbar):
    ''' Adds link to School Stats to Events toolbar menu '''

    def populate(self):
        if self.request.user.has_perm('core.view_school_stats'):
            try:
                reverse('schoolStatsView')
            except NoReverseMatch:
                return

            menu = self.toolbar.get_or_create_menu('core-events',_('Events'))
            position = menu.find_first(SubMenu, identifier='core-events-related') or 0
            menu.add_break('post_related_events_break', position=position + 1)
            menu.add_link_item(_('View School Performance Stats'), reverse('schoolStatsView'), position=position + 2)
