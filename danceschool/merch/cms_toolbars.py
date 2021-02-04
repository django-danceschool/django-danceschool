# Third Party Imports
from cms.toolbar_base import CMSToolbar
from cms.toolbar.items import Break
from cms.toolbar_pool import toolbar_pool
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import MerchItem, MerchOrder


@toolbar_pool.register
class MerchToolbar(CMSToolbar):
    ''' Adds submenu for merchandise '''

    def populate(self):
        menu = self.toolbar.get_or_create_menu('door-register', _('Registration'))

        if (
            self.request.user.has_perm('merch.change_merchitem') or
            self.request.user.has_perm('merch.change_merchorder')            
        ):
            merch_menu = menu.get_or_create_menu('merch', _('Merchandise'))
        else:
            return

        if self.request.user.has_perm('merch.change_merchitem'):
            merch_menu.add_link_item(
                _('Items'),
                url=reverse('admin:merch_merchitem_changelist')
            )

        if self.request.user.has_perm('merch.change_merchorder'):
            merch_menu.add_link_item(
                _('Orders'),
                url=reverse('admin:merch_merchorder_changelist')
            )
