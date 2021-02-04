from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar
from cms.toolbar.items import LinkItem
from cms.constants import RIGHT

from danceschool.core.utils.timezone import ensure_localtime
from .models import DoorRegister


@toolbar_pool.register
class DoorToolbar(CMSToolbar):
    ''' Adds links to Events for today's cash registers '''

    def populate(self):
        menu = self.toolbar.get_or_create_menu('door-register', _('Registration'))

        if self.request.user.has_perm('core.accept_door_payments'):
            today = ensure_localtime(timezone.now())

            registers = DoorRegister.objects.filter(enabled=True)

            for register in registers:
                url = reverse('doorRegister', args=(register.slug, today.year, today.month, today.day))
                menu.add_link_item(register.title, url=url)

            if registers:
                menu.add_break('post-registers-break')

        if self.request.user.has_perm('core.view_registration_summary'):
            menu.add_link_item(_('View Registrations'), url=reverse('viewregistrations_selectevent'))

        menu.add_link_item(_('Registration Page'), url=reverse('registration'))

        if self.request.user.has_perm('door.change_doorregister'):
            menu.add_link_item(_('Manage Registers'), url=reverse('admin:door_doorregister_changelist'))
        if self.request.user.has_perm('door.change_doorregisterpaymentmethod'):
            menu.add_link_item(
                _('Manage Register Payment Methods'),
                url=reverse('admin:door_doorregisterpaymentmethod_changelist')
            )
