# Third Party Imports
from cms.toolbar_base import CMSToolbar
from cms.toolbar.items import Break
from cms.toolbar_pool import toolbar_pool
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _


@toolbar_pool.register
class BanlistToolbar(CMSToolbar):
    ''' Adds link to School Stats to Events toolbar menu '''

    def populate(self):
        menu = self.toolbar.get_or_create_menu('core-events', _('Events'))

        break_index = menu.find_first(Break, identifier='related_items_break').index

        if self.request.user.has_perm('banlist.view_banlist'):
            banlist_menu = menu.get_or_create_menu('banlist', _('Banned Individuals'), position=break_index + 1)
            banlist_menu.add_link_item(_('View Banned Individuals List'), url=reverse('viewBanList'))

        if self.request.user.has_perm('banlist.change_bannedperson'):
            banlist_menu = menu.get_or_create_menu('banlist', _('Banned Individuals'), position=break_index + 1)
            banlist_menu.add_link_item(_('Manage Banned Individuals List'),
                                       url=reverse('admin:banlist_bannedperson_changelist'))

        if self.request.user.has_perm('banlist.change_banflaggedrecord'):
            banlist_menu = menu.get_or_create_menu('banlist', _('Banned Individuals'), position=break_index + 1)
            banlist_menu.add_link_item(_('View Registration Attempts'),
                                       url=reverse('admin:banlist_banflaggedrecord_changelist'))
