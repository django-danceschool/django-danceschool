from django.core.management.base import BaseCommand
from django.apps import apps
from django.contrib.auth.models import Group, Permission

from six.moves import input

try:
    import readline
except ImportError:
    pass


class Command(BaseCommand):
    help = 'Create default groups and permissions for standard dance school setups'

    def boolean_input(self, question, default=None):
        '''
        Method for yes/no boolean inputs
        '''
        result = input("%s: " % question)
        if not result and default is not None:
            return default
        while len(result) < 1 or result[0].lower() not in "yn":
            result = input("Please answer yes or no: ")
        return result[0].lower() == "y"

    def handle(self, *args, **options):

        self.stdout.write(
            """
USER GROUPS AND PERMISSIONS
---------------------------

This project allows you to provide finely-grained permissions to individual users and
user groups, such as instructors and administrators.  This allows you to let different
types of users manage different types of content while still maintaining appropriate
security.

To get you started with the permissions system, we can create three initial user
groups, and give them different levels of permissions over content:

 - The "Board" group: Users in this group will receive permissions to edit
all public-facing content as well as all financial records.  They will not
automaticcaly receive permissions to edit certain other sitewide settings for
security reasons.
 - The "Instructor" group: Users in this group will receive permissions to use
school administrative functions such as emailing students, submitting expenses
and revenues, and viewing their own statistics and payment history.  However, by
default, these users cannot edit public-facing content such as page content or
FAQs.
 - The "Registration Desk" group: Users in this group receive only the ability
 to log into the site in order to view class registrations and check in students.
 By default, they cannot access any other administrative function.

We strongly encourage you to create these initial groups as a starting point for
managing staff permissions on the site.  The superuser that you created previously
will always retain permissions to edit all content and settings.  Additionally, you
can always go on to create additional groups, or to edit permissions on either a
group basis or an individual user basis.

Note: This process may take a minute or two to complete.

            """
        )

        create_board_group = self.boolean_input('Create \'Board\' group with default initial permissions [Y/n]', True)
        if create_board_group:
            board_group = Group.objects.get_or_create(name='Board')[0]

            # The Board group get all permissions on the CMS app and on all danceschool apps, plus
            # the permissions explicitly listed here by their natural_key.  Unfortunately this is
            # slow because we have to check permissions one-by-one
            give_explicit = [
                ('add_emailaddress', 'account', 'emailaddress'),
                ('change_emailaddress', 'account', 'emailaddress'),
                ('delete_emailaddress', 'account', 'emailaddress'),
                ('add_user', 'auth', 'user'),
                ('change_user', 'auth', 'user'),
            ]

            app_add_list = ['cms','core','djangocms_forms','djangocms_text_ckeditor','easy_thumbnails','filer']
            for this_app in [
                'danceschool.financial',
                'danceschool.discounts',
                'danceschool.faq',
                'danceschool.news',
                'danceschool.prerequisites',
                'danceschool.private_events',
                'danceschool.private_lessons',
                'danceschool.stats',
                'danceschool.vouchers',
                'danceschool.banlist',
                'danceschool.payments.paypal',
                'danceschool.payments.stripe',
            ]:
                if apps.is_installed(this_app):
                    app_add_list.append(this_app.split('.')[1])

            for perm in Permission.objects.all():
                if perm.natural_key() in give_explicit or perm.natural_key()[1] in app_add_list:
                    board_group.permissions.add(perm)
            self.stdout.write('Finished creating \'Board\' group and setting initial permissions.\n')

        create_instructor_group = self.boolean_input('Create \'Instructor\' group with default initial permissions [Y/n]', True)
        if create_instructor_group:
            instructor_group = Group.objects.get_or_create(name='Instructor')[0]

            give_explicit = [
                ('view_page', 'cms', 'page'),
                ('add_classdescription', 'core', 'classdescription'),
                ('change_classdescription', 'core', 'classdescription'),
                ('can_autocomplete_users', 'core', 'customer'),
                ('send_email', 'core', 'emailtemplate'),
                ('report_substitute_teaching', 'core', 'eventstaffmember'),
                ('update_instructor_bio', 'core', 'instructor'),
                ('view_own_instructor_finances', 'core', 'instructor'),
                ('view_own_instructor_stats', 'core', 'instructor'),
                ('process_refunds','core','invoice'),
                ('send_invoices', 'core', 'invoice'),
                ('view_all_invoices','core','invoice'),
                ('accept_door_payments', 'core', 'registration'),
                ('checkin_customers', 'core', 'registration'),
                ('override_register_closed', 'core', 'registration'),
                ('override_register_dropins', 'core', 'registration'),
                ('override_register_soldout', 'core', 'registration'),
                ('register_dropins', 'core', 'registration'),
                ('view_registration_summary', 'core', 'registration'),
                ('view_school_stats', 'core', 'staffmember'),
                ('view_staff_directory', 'core', 'staffmember'),
                ('add_file', 'filer', 'file'),
                ('change_file', 'filer', 'file'),
                ('can_use_directory_listing', 'filer', 'folder'),
                ('add_image', 'filer', 'image'),
                ('change_image', 'filer', 'image'),
                ('add_expenseitem', 'financial', 'expenseitem'),
                ('mark_expenses_paid', 'financial', 'expenseitem'),
                ('add_revenueitem', 'financial', 'revenueitem'),
                ('view_finances_bymonth', 'financial', 'revenueitem'),
                ('add_newsitem', 'news', 'newsitem'),
                ('change_newsitem', 'news', 'newsitem'),
                ('ignore_requirements', 'prerequisites', 'requirement'),
                ('add_eventreminder', 'private_events', 'eventreminder'),
                ('change_eventreminder', 'private_events', 'eventreminder'),
                ('delete_eventreminder', 'private_events', 'eventreminder'),
                ('add_privateevent', 'private_events', 'privateevent'),
                ('change_privateevent', 'private_events', 'privateevent'),
                ('delete_privateevent', 'private_events', 'privateevent'),
                ('edit_own_availability', 'private_lessons', 'instructoravailabilityslot'),
                ('view_banlist', 'banlist','bannedperson'),
            ]

            for perm in Permission.objects.all():
                if perm.natural_key() in give_explicit:
                    instructor_group.permissions.add(perm)
            self.stdout.write('Finished creating \'Instructor\' group and setting initial permissions.\n')

        create_regdesk_group = self.boolean_input('Create \'Registration Desk\' group with default initial permissions [Y/n]', True)
        if create_regdesk_group:
            regdesk_group = Group.objects.get_or_create(name='Registration Desk')[0]

            give_explicit = [
                ('view_page', 'cms', 'page'),
                ('can_autocomplete_users', 'core', 'customer'),
                ('process_refunds','core','invoice'),
                ('send_invoices', 'core', 'invoice'),
                ('view_all_invoices','core','invoice'),
                ('accept_door_payments', 'core', 'registration'),
                ('checkin_customers', 'core', 'registration'),
                ('override_register_closed', 'core', 'registration'),
                ('override_register_dropins', 'core', 'registration'),
                ('override_register_soldout', 'core', 'registration'),
                ('register_dropins', 'core', 'registration'),
                ('view_registration_summary', 'core', 'registration'),
                ('view_staff_directory', 'core', 'staffmember'),
                ('ignore_requirements', 'prerequisites', 'requirement'),
                ('view_banlist', 'banlist','bannedperson'),
            ]

            for perm in Permission.objects.all():
                if perm.natural_key() in give_explicit:
                    regdesk_group.permissions.add(perm)
            self.stdout.write('Finished creating \'Registration\' group and setting initial permissions.\n')
