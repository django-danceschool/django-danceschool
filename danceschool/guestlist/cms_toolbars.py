# Third Party Imports
from cms.toolbar_base import CMSToolbar
from cms.toolbar.items import Break
from cms.toolbar_pool import toolbar_pool
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import GuestList


@toolbar_pool.register
class GuestListToolbar(CMSToolbar):
    ''' Adds submenu for guest lists '''

    def populate(self):
        menu = self.toolbar.get_or_create_menu('core-events', _('Events'))

        position = menu.find_first(Break, identifier='related_items_break')

        if not position:
            menu.add_break('related_items_break')
            position = menu.find_first(Break, identifier='related_items_break')

        if (
            self.request.user.has_perm('guestlist.view_guestlist') or
            self.request.user.has_perm('guestlist.change_guestlist')
        ):
            guestlist_menu = menu.get_or_create_menu('guestlist', _('Guest Lists'), position=position + 1)
        else:
            return

        if self.request.user.has_perm('guestlist.view_guestlist'):
            for thisList in GuestList.objects.all():
                guestlist_menu.add_link_item(
                    thisList.name,
                    url=reverse('viewGuestList', args=(thisList.id,))
                )

        if self.request.user.has_perm('guestlist.change_guestlist'):
            guestlist_menu.add_break('manage-break')
            guestlist_menu.add_link_item(
                _('Manage Guest Lists'),
                url=reverse('admin:guestlist_guestlist_changelist')
            )
