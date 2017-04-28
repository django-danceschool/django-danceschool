from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar
from cms.toolbar.items import Break


@toolbar_pool.register
class PaypalLinksToolbar(CMSToolbar):
    ''' Add Paypal items to the financial menu '''

    def populate(self):
        if not (self.request.user.has_perm('paypal.change_ipnmessage') or self.request.user.has_perm('paypal.change_invoice')):
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

        if self.request.user.has_perm('paypal.change_ipnmessage'):
            related_menu.add_link_item(_('Paypal IPN Messages'), url=reverse('admin:paypal_ipnmessage_changelist'))
        if self.request.user.has_perm('paypal.change_invoice'):
            related_menu.add_link_item(_('Paypal Submitted Invoices'), url=reverse('admin:paypal_invoice_changelist'))
