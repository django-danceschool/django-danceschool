from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar


@toolbar_pool.register
class NewsItemContentToolbar(CMSToolbar):
    ''' Adds link to FAQs to Content toolbar menu '''

    def populate(self):
        if self.request.user.has_perm('news.add_newsitem'):
            menu = self.toolbar.get_or_create_menu('core-content',_('Content'))
            menu.add_link_item(_('Add News Item'), reverse('admin:news_newsitem_add'), position=0)
            menu.add_break('post_add_newsitem_break', position=1)
            menu.add_link_item(_('Manage News Items'), reverse('admin:news_newsitem_changelist'))
