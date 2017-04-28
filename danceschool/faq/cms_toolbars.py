from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar


@toolbar_pool.register
class FAQContentToolbar(CMSToolbar):
    ''' Adds link to FAQs to Content toolbar menu '''

    def populate(self):
        if self.request.user.has_perm('faq.change_faq'):
            menu = self.toolbar.get_or_create_menu('core-content',_('Content'))
            menu.add_link_item(_('Manage FAQs'), reverse('admin:faq_faq_changelist'))
