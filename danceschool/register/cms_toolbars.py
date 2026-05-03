from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar

from danceschool.core.utils.timezone import ensure_localtime
from .models import Register


@toolbar_pool.register
class RegisterToolbar(CMSToolbar):
    ''' Adds links to Events for today's cash registers '''

    def populate(self):
        menu = self.toolbar.get_or_create_menu('door-register', _('Registration'))

        # When viewing a register page, set the object so CMS shows Edit/Structure
        # buttons for that register's placeholder.
        resolver_match = getattr(self.request, 'resolver_match', None)
        if resolver_match and resolver_match.url_name == 'registerView':
            slug = resolver_match.kwargs.get('slug')
            if slug:
                try:
                    register = Register.objects.get(slug=slug, enabled=True)
                    self.toolbar.set_object(register)
                except Register.DoesNotExist:
                    pass

        if self.request.user.has_perm('core.accept_door_payments'):
            today = ensure_localtime(timezone.now())

            registers = Register.objects.filter(enabled=True)

            for register in registers:
                url = reverse('registerView', args=(register.slug, today.year, today.month, today.day))
                menu.add_link_item(register.title, url=url)

            if registers:
                menu.add_break('post-registers-break')

        if self.request.user.has_perm('core.view_registration_summary'):
            menu.add_link_item(_('View Registrations'), url=reverse('viewregistrations_selectevent'))

        menu.add_link_item(_('Registration Page'), url=reverse('registration'))

        if self.request.user.has_perm('door.change_register'):
            menu.add_link_item(_('Manage Registers'), url=reverse('admin:register_register_changelist'))
        if self.request.user.has_perm('door.change_registerpaymentmethod'):
            menu.add_link_item(
                _('Manage Register Payment Methods'),
                url=reverse('admin:register_registerpaymentmethod_changelist')
            )
