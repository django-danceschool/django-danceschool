from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from dateutil.relativedelta import relativedelta
from calendar import month_name

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar
from cms.toolbar.items import Break


@toolbar_pool.register
class FinancialToolbar(CMSToolbar):
    ''' Adds links to financial functions '''

    def addTheMenu(self):
        ''' Since not all staff users get this menu, this function simplifies its creation '''

        menu = self.toolbar.get_or_create_menu('financial', _('Finances'))

        # Other apps may add related items, so check if those exist yet, and if so, add before them
        startPosition = menu.find_first(
            Break,
            identifier='financial_related_items_break'
        )

        if not startPosition:
            menu.add_break('financial_related_items_break')
            startPosition = menu.find_first(
                Break,
                identifier='financial_related_items_break'
            )
        return (menu, startPosition)

    def populate(self):
        menu = None
        addBreak = False
        if self.request.user.has_perm('financial.add_expenseitem'):
            menu, newPosition = self.addTheMenu()
            menu.add_link_item(_('Submit Expenses'), url=reverse('submitExpenses'), position=newPosition)
            addBreak = True
        if self.request.user.has_perm('financial.add_revenueitem'):
            menu, newPosition = self.addTheMenu()
            menu.add_link_item(_('Submit Revenues'), url=reverse('submitRevenues'), position=newPosition)
            addBreak = True
        if hasattr(self.request.user,'staffmember') and self.request.user.staffmember and self.request.user.has_perm('core.view_own_instructor_finances'):
            menu, newPosition = self.addTheMenu()
            menu.add_link_item(_('Your Payment History'), url=reverse('instructorPayments'), position=newPosition)

        if addBreak:
            menu.add_break('post_submission_break', position=newPosition + 1)

        if self.request.user.has_perm('financial.view_finances_bymonth'):
            menu, newPosition = self.addTheMenu()
            menu.add_link_item(_('View Monthly Financial Summary'), url=reverse('financesByMonth'), position=newPosition)
        if self.request.user.has_perm('financial.view_finances_byevent'):
            menu, newPosition = self.addTheMenu()
            menu.add_link_item(_('View Financial Summary By Event'), url=reverse('financesByEvent'), position=newPosition)

        if self.request.user.has_perm('financial.view_finances_detail'):
            menu, newPosition = self.addTheMenu()
            detail_submenu = menu.get_or_create_menu('financial-details',_('Detailed Breakdown'), position=newPosition)

            now = timezone.now()
            month_ago = now - relativedelta(months=1)
            two_months_ago = now - relativedelta(months=2)
            three_months_ago = now - relativedelta(months=3)
            year_ago = now - relativedelta(years=1)

            detail_submenu.add_link_item(_('Year To Date'), url=reverse('financialDetailView', kwargs={'year': str(now.year)}))
            detail_submenu.add_link_item(_('%s' % year_ago.year), url=reverse('financialDetailView',kwargs={'year': str(year_ago.year)}))

            detail_submenu.add_break('post_annual_break')

            detail_submenu.add_link_item(_('Month To Date'), url=reverse('financialDetailView',kwargs={'year': str(now.year), 'month': month_name[now.month]}))
            detail_submenu.add_link_item(_('%s %s' % (month_name[month_ago.month], month_ago.year)), url=reverse('financialDetailView',kwargs={'year': str(month_ago.year), 'month': month_name[month_ago.month]}))
            detail_submenu.add_link_item(_('%s %s' % (month_name[two_months_ago.month], two_months_ago.year)), url=reverse('financialDetailView',kwargs={'year': str(two_months_ago.year), 'month': month_name[two_months_ago.month]}))
            detail_submenu.add_link_item(_('%s %s' % (month_name[three_months_ago.month], three_months_ago.year)), url=reverse('financialDetailView',kwargs={'year': str(three_months_ago.year), 'month': month_name[three_months_ago.month]}))

        if menu and (
            self.request.user.has_perm('financial.change_expenseitem') or self.request.user.has_perm('financial.change_revenueitem') or
            self.request.user.has_perm('financial.change_expensecategory') or self.request.user.has_perm('financial.change_revenuecategory') or
            self.request.user.has_perm('financial.change_repeatedexpenserule')
        ):
            related_menu = menu.get_or_create_menu('financial-related',_('Related Items'), position=newPosition + 2)

            if self.request.user.has_perm('financial.change_expensecategory'):
                related_menu.add_link_item(_('Expense Categories'), url=reverse('admin:financial_expensecategory_changelist'))
            if self.request.user.has_perm('financial.change_expenseitem'):
                related_menu.add_link_item(_('Expense Items'), url=reverse('admin:financial_expenseitem_changelist'))
            if self.request.user.has_perm('financial.change_repeatedexpenserule'):
                related_menu.add_link_item(_('Repeated Expense Rules'), url=reverse('admin:financial_repeatedexpenserule_changelist'))
            if self.request.user.has_perm('financial.change_revenuecategory'):
                related_menu.add_link_item(_('Revenue Categories'), url=reverse('admin:financial_revenuecategory_changelist'))
            if self.request.user.has_perm('financial.change_revenueitem'):
                related_menu.add_link_item(_('Revenue Items'), url=reverse('admin:financial_revenueitem_changelist'))
