from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar
from cms.toolbar.items import BaseItem


@toolbar_pool.register
class PrivateLessonsToolbar(CMSToolbar):
    ''' Adds private events links to the Staff toolbar and category links to the related items toolbar '''

    def populate(self):
        staff_menu = self.toolbar.get_or_create_menu('core-staffmember',_('Staff'))

        if (
            hasattr(self.request.user,'staffmember') and
            self.request.user.staffmember.instructor and
            self.request.user.staffmember.feedKey
        ):
            position = staff_menu.find_first(BaseItem,name=_('Your Stats')) or 0
            staff_menu.add_link_item(_('Private Lesson Availability'), url=reverse('instructorAvailability'), position=position + 1)
