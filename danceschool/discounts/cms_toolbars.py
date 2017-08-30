from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar
from cms.toolbar.items import Break


@toolbar_pool.register
class DiscountLinksToolbar(CMSToolbar):
    ''' Add discounts to the financial menu '''

    def populate(self):
        if not (
            self.request.user.has_perm('discounts.change_discountcombo') or
            self.request.user.has_perm('discounts.change_discountcategory')
        ):
            return

        financial_menu = self.toolbar.get_or_create_menu(
            'financial', _('Finances'))

        position = financial_menu.find_first(
            Break,
            identifier='financial_related_items_break'
        )

        if not position:
            financial_menu.add_break('financial_related_items_break')
            position = financial_menu.find_first(
                Break,
                identifier='financial_related_items_break'
            ) + 1

        related_menu = financial_menu.get_or_create_menu('financial-related',_('Related Items'), position=position)

        if self.request.user.has_perm('discounts.change_discountcombo'):
            related_menu.add_link_item(_('Discounts'), url=reverse('admin:discounts_discountcombo_changelist'))
        if self.request.user.has_perm('discounts.change_discountcategory'):
            related_menu.add_link_item(_('Discount Categories'), url=reverse('admin:discounts_discountcategory_changelist'))
