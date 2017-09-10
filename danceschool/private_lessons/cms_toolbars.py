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
        position = staff_menu.find_first(BaseItem,name=_('Your Stats')) or 0

        staff_menu.add_link_item(_('Schedule a Private Lesson'), url=reverse('bookPrivateLesson'), position=position + 1)

        if (
            self.request.user.has_perm('private_lessons.edit_own_availability') or
            self.request.user.has_perm('private_lessons.edit_others_availability')
        ):
            staff_menu.add_link_item(_('Private Lesson Availability'), url=reverse('instructorAvailability'), position=position + 1)
