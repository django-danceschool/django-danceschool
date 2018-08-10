from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from django.apps import apps

from cms.toolbar_pool import toolbar_pool
from cms.toolbar_base import CMSToolbar
from cms.toolbar.items import Break, SubMenu
from cms.cms_toolbars import ADMIN_MENU_IDENTIFIER, ADMINISTRATION_BREAK
from cms.constants import RIGHT


@toolbar_pool.register
class SettingsToolbar(CMSToolbar):
    ''' Adds a link to the Global settings page '''

    def populate(self):
        #
        # 'Apps' is the spot on the existing djang-cms toolbar admin_menu
        # 'where we'll insert all of our applications' menus.
        #
        if not self.request.user.has_perm('dynamic_preferences.change_global_preference'):
            return

        admin_menu = self.toolbar.get_or_create_menu(
            ADMIN_MENU_IDENTIFIER, _('Apps'))

        position = admin_menu.get_alphabetical_insert_position(
            _('Global Settings'),
            SubMenu
        )

        #
        # If zero was returned, then we know we're the first of our
        # applications' menus to be inserted into the admin_menu, so, here
        # we'll compute that we need to go after the first
        # ADMINISTRATION_BREAK and, we'll insert our own break after our
        # section.
        #
        if not position:
            # OK, use the ADMINISTRATION_BREAK location + 1
            position = admin_menu.find_first(
                Break,
                identifier=ADMINISTRATION_BREAK
            ) + 1
            # Insert our own menu-break, at this new position. We'll insert
            # all subsequent menus before this, so it will ultimately come
            # after all of our applications' menus.
            admin_menu.add_break('custom-break', position=position)

        # OK, create the global settings menu here
        admin_menu.add_link_item(
            _('Global Settings'), url=reverse('dynamic_preferences.global'),
            position=position
        )


@toolbar_pool.register
class EventsToolbar(CMSToolbar):
    ''' Adds items to the toolbar to add class Series and Events, etc, as well as a button to view registrations '''

    def populate(self):
        menu = self.toolbar.get_or_create_menu('core-events', _('Events'))

        if self.request.user.has_perm('core.view_registration_summary'):
            self.toolbar.add_button(_('View Registrations'), url=reverse('viewregistrations_selectevent'),side=RIGHT)

            menu.add_link_item(_('View Registrations'), url=reverse('viewregistrations_selectevent'))

        menu.add_link_item(_('Registration Page'), url=reverse('registration'))

        if (
            self.request.user.has_perm('core.add_series') or
            self.request.user.has_perm('core.add_publicevent') or
            self.request.user.has_perm('core.change_series') or
                self.request.user.has_perm('core.change_publicevent')):
                menu.add_break('post_registration_break')
                if self.request.user.has_perm('core.add_series'):
                    menu.add_link_item(_('Add a Class Series'), url=reverse('admin:core_series_add'))
                if self.request.user.has_perm('core.add_publicevent'):
                    menu.add_link_item(_('Add a Public Event'), url=reverse('admin:core_publicevent_add'))
                if self.request.user.has_perm('core.add_series'):
                    menu.add_link_item(_('Edit Existing Series'), url=reverse('admin:core_series_changelist'))
                if self.request.user.has_perm('core.add_publicevent'):
                    menu.add_link_item(_('Edit Existing Events'), url=reverse('admin:core_publicevent_changelist'))

        if self.request.user.has_perm('core.change_classdescription') or self.request.user.has_perm('core.change_dancetypelevel') \
            or self.request.user.has_perm('core.change_location') or self.request.user.has_perm('core.change_pricingtier') or \
                self.request.user.has_perm('core.change_customer') or self.request.user.has_perm('core.change_dancerole') or \
                self.request.user.has_perm('core.change_publiceventcategory') or self.request.user.has_perm('core.change_eventstaffcategory'):
                    menu.add_break('related_items_break')

        if self.request.user.has_perm('core.change_classdescription'):
            related_menu = menu.get_or_create_menu('core-events-related',_('Related Items'))
            related_menu.add_link_item(_('Class Descriptions'),url=reverse('admin:core_classdescription_changelist'))

        if self.request.user.has_perm('core.change_customer'):
            related_menu = menu.get_or_create_menu('core-events-related',_('Related Items'))
            related_menu.add_link_item(_('Customers'),url=reverse('admin:core_customer_changelist'))

        if self.request.user.has_perm('core.change_customergroup'):
            related_menu = menu.get_or_create_menu('core-events-related',_('Related Items'))
            related_menu.add_link_item(_('Customer Groups'),url=reverse('admin:core_customergroup_changelist'))

        if self.request.user.has_perm('core.change_dancetypelevel'):
            related_menu = menu.get_or_create_menu('core-events-related',_('Related Items'))
            related_menu.add_link_item(_('Dance Roles'),url=reverse('admin:core_dancerole_changelist'))

        if self.request.user.has_perm('core.change_dancetypelevel'):
            related_menu = menu.get_or_create_menu('core-events-related',_('Related Items'))
            related_menu.add_link_item(_('Dance Types/Levels'),url=reverse('admin:core_dancetypelevel_changelist'))

        if self.request.user.has_perm('core.change_eventstaffcategory'):
            related_menu = menu.get_or_create_menu('core-events-related',_('Related Items'))
            related_menu.add_link_item(_('Event Staff Categories'),url=reverse('admin:core_eventstaffcategory_changelist'))

        if self.request.user.has_perm('core.change_location'):
            related_menu = menu.get_or_create_menu('core-events-related',_('Related Items'))
            related_menu.add_link_item(_('Locations'),url=reverse('admin:core_location_changelist'))

        if self.request.user.has_perm('core.change_pricingtier'):
            related_menu = menu.get_or_create_menu('core-events-related',_('Related Items'))
            related_menu.add_link_item(_('Pricing Tiers'),url=reverse('admin:core_pricingtier_changelist'))

        if self.request.user.has_perm('core.change_publiceventcategory'):
            related_menu = menu.get_or_create_menu('core-events-related',_('Related Items'))
            related_menu.add_link_item(_('Public Event Categories'),url=reverse('admin:core_publiceventcategory_changelist'))


@toolbar_pool.register
class StaffMemberToolbar(CMSToolbar):
    ''' Adds items to the toolbar to add class Series and Events. '''

    def populate(self):
        if hasattr(self.request.user,'staffmember') and hasattr(self.request.user.staffmember,'instructor') and self.request.user.has_perm('core.view_own_instructor_stats'):
            menu = self.toolbar.get_or_create_menu('core-staffmember', _('Staff'))
            menu.add_link_item(_('Your Stats'), url=reverse('instructorStats'))
        if hasattr(self.request.user,'staffmember') and self.request.user.has_perm('core.update_instructor_bio'):
            menu = self.toolbar.get_or_create_menu('core-staffmember', _('Staff'))
            menu.add_link_item(_('Update Your Contact Info'), url=reverse('instructorBioChange'))

        if self.request.user.has_perm('core.view_staff_directory'):
            menu = self.toolbar.get_or_create_menu('core-staffmember', _('Staff'))
            menu.add_link_item(_('Instructor/Staff Directory'), url=reverse('staffDirectory'))
            menu.add_break('post_directory_break')

        addBreak = False

        if self.request.user.has_perm('core.send_email'):
            menu = self.toolbar.get_or_create_menu('core-staffmember', _('Staff'))
            menu.add_link_item(_('Email Students'), url=reverse('emailStudents'))
            addBreak = True

        if self.request.user.has_perm('core.report_substitute_teaching'):
            menu = self.toolbar.get_or_create_menu('core-staffmember', _('Staff'))
            menu.add_link_item(_('Report Substitute Teaching'), url=reverse('substituteTeacherForm'))
            addBreak = True

        if addBreak:
            menu.add_break('post_instructor_functions_break')

        if self.request.user.has_perm('core.change_instructor'):
            menu = self.toolbar.get_or_create_menu('core-staffmember', _('Staff'))
            menu.add_link_item(_('Manage Instructors'), url=reverse('admin:core_instructor_changelist'))


@toolbar_pool.register
class ContentToolbar(CMSToolbar):
    ''' Adds links to manage files, and can be hooked in to manage News, FAQs, Surveys/Forms, etc. '''

    def populate(self):
        if (
            self.request.user.has_perm('filer.change_folder') or self.request.user.has_perm('core.change_emailtemplate') or
            (apps.is_installed('djangocms_forms') and self.request.user.has_perm('djangocms_forms.export_formsubmission'))
        ):
            menu = self.toolbar.get_or_create_menu('core-content',_('Content'))

        if self.request.user.has_perm('filer.change_folder'):
            menu.add_link_item(_('Manage Uploaded Files'), reverse('admin:filer_folder_changelist'))

        if self.request.user.has_perm('core.change_emailtemplate'):
            menu.add_link_item(_('Manage Email Templates'), reverse('admin:core_emailtemplate_changelist'))

        if apps.is_installed('djangocms_forms') and self.request.user.has_perm('djangocms_forms.export_formsubmission'):
            menu.add_link_item(_('View/Export Survey Responses'), reverse('admin:djangocms_forms_formsubmission_changelist'))


@toolbar_pool.register
class CoreFinancesToolbar(CMSToolbar):
    ''' Adds links to view and add invoices '''

    def populate(self):
        if (
            self.request.user.has_perm('core.add_invoice')
        ):
            menu = self.toolbar.get_or_create_menu('financial', _('Finances'))

            # The "Create an Invoice" link goes at the top of the menu
            menu.add_link_item(_('Create an Invoice'), url=reverse('admin:core_invoice_add'),position=0)

            # Other apps may have added related items already
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
            related_menu = menu.get_or_create_menu('financial-related',_('Related Items'), position=startPosition + 2)
            related_menu.add_link_item(_('Invoices'), url=reverse('admin:core_invoice_changelist'))
