from django.core.management.base import BaseCommand
from django.apps import apps
from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User, Group, Permission
from django.contrib.sites.models import Site

from danceschool.core.models import DanceType, DanceTypeLevel, DanceRole, PricingTier, InstructorListPluginModel

from dynamic_preferences.registries import global_preferences_registry
import re
from six.moves import input
from importlib import import_module

try:
    import readline
except ImportError:
    pass


class Command(BaseCommand):
    help = 'Easy-install setup script for new dance schools'

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

    def pattern_input(self, question, message='Invalid entry', pattern='^[a-zA-Z0-9_ ]+$', default='',required=True):
        '''
        Method for input disallowing special characters, with optionally
        specifiable regex pattern and error message.
        '''
        result = ''
        requiredFlag = True

        while (not result and requiredFlag):
            result = input('%s: ' % question)
            if result and pattern and not re.match(pattern, result):
                self.stdout.write(self.style.ERROR(message))
                result = ''
            elif not result and default:
                # Return default for fields with default
                return default
            elif not result and required:
                # Ask again for required fields
                self.stdout.write(self.style.ERROR('Answer is required.'))
            elif not required:
                # No need to re-ask for non-required fields
                requiredFlag = False
        return result

    def float_input(self, question, message='Invalid entry', default=None, required=True):
        '''
        Method for floating point inputs with optionally specifiable error message.
        '''
        float_result = None
        requiredFlag = True

        while (float_result is None and requiredFlag):
            result = input('%s: ' % question)
            if not result and not required:
                float_result = None
                requiredFlag = False
            if not result and default:
                float_result = default

            if float_result is None and requiredFlag:
                try:
                    float_result = float(result)
                except ValueError:
                    self.stdout.write(self.style.ERROR(message))
                    float_result = None
        return float_result

    def handle(self, *args, **options):

        from cms.api import create_page, add_plugin, publish_page
        from cms.constants import VISIBILITY_ANONYMOUS, VISIBILITY_USERS
        from cms.models import Page, StaticPlaceholder

        prefs = global_preferences_registry.manager()

        # Do some sanity checks to ensure that necessary apps are listed in INSTALLED_APPS
        # before proceeding
        required_apps = [
            ('cms', 'Django CMS'),
            ('danceschool.core', 'Core danceschool app'),
            ('dynamic_preferences', 'django-dynamic-preferences'),
        ]
        for this_app in required_apps:
            if not apps.is_installed(this_app[0]):
                self.stdout.write(self.style.ERROR('ERROR: %s is not installed or listed in INSTALLED_APPS. Please install before proceeding.' % this_app[1]))
                return None

        this_user = User.objects.filter(is_superuser=True).first()
        if not this_user:
            self.stdout.write(self.style.ERROR('ERROR: Superuser has not yet been created.  Please run \'python manage.py createsuperuser\' before proceeding.'))
            return None

        if Page.objects.count() > 0:
            self.stdout.write(self.style.WARNING('WARNING: CMS pages have already been created.  Creating duplicate CMS pages may lead to unexpected results.'))

        self.stdout.write(
            """
WELCOME
-------

Welcome to the django-danceschool setup script. This script is designed to guide you
through the setup of many key parameters and initial defaults that will make your
experience simpler and faster.

All inputs of this script can be later changed using the site's admin interface, so
if you decide that you need to change something later, you should not need to run this
script again.

Please answer the following questions (defaults values are in brackets)


BASIC SETUP:
------------
            """
        )

        # Current Domain
        current_domain = self.pattern_input(
            'Enter the domain name of this installation, with no protocol or trailing slashes (e.g. \'bostonlindyhop.com\') [localhost:8000]',
            message='Invalid domain name (no whitespace or slashes allowed)',
            default='localhost:8000',
            pattern='^[^/\\ ]+$'
        )
        this_site = Site.objects.get_current()
        this_site.name = current_domain
        this_site.domain = current_domain
        this_site.save()

        # School name
        school_name = self.pattern_input(
            'Give your dance school a name [Dance School]',
            message='Invalid school name (no special characters allowed)',
            default='Dance School'
        )
        prefs['contact__businessName'] = school_name
        prefs['email__defaultEmailName'] = school_name

        # School Email
        school_email = self.pattern_input(
            'Provide a default school email address',
            message='Invalid email address.',
            pattern='^[^@]+@[^@]+\.[^@]+$',
        )
        prefs['contact__businessEmail'] = school_email
        prefs['email__defaultEmailFrom'] = school_email
        prefs['email__errorEmailFrom'] = school_email

        # School Phone and Address
        school_phone = input('Provide a phone number for the school (optional): ')
        if school_phone:
            prefs['contact__businessPhone'] = school_phone

        school_address1 = input('Enter school street address - Line 1 (optional): ')
        if school_address1:
            prefs['contact__businessAddress'] = school_address1

        school_address2 = input('Enter school street address - Line 2 (optional): ')
        if school_address2:
            prefs['contact__businessAddressLineTwo'] = school_address2

        school_city = self.pattern_input(
            'Enter school city [Boston]',
            message='Invalid city (no special characters allowed)',
            pattern='^[a-zA-Z0-9 ]+$',
            default='Boston',
        )
        prefs['contact__businessCity'] = school_city

        school_state = self.pattern_input(
            'Enter school state [MA]',
            message='Invalid state (no special characters allowed)',
            pattern='^[a-zA-Z0-9 ]+$',
            default='MA',
        )
        prefs['contact__businessState'] = school_state

        school_postal = input('Enter school ZIP/postal code [02114]: ') or '02114'
        prefs['contact__businessZip'] = school_postal

        school_country = self.pattern_input(
            'Enter two-letter school country code [US]',
            message='Invalid state (only two uppercase letters allowed)',
            pattern='^[A-Z][A-Z]$',
            default='US',
        )
        prefs['contact__businessCountryCode'] = school_country

        currency_code = self.pattern_input(
            'Enter three-letter currency code for transactions [USD]',
            message='Invalid currency code (only three uppercase letters allowed)',
            pattern='^[A-Z][A-Z][A-Z]$',
            default='USD',
        )
        prefs['general__currencyCode'] = currency_code

        currency_symbol = input('Unicode currency symbol for display [$]: ') or '$'
        prefs['general__currencySymbol'] = currency_symbol

        send_error_emails = self.boolean_input('Send error emails [Y/n]',True)
        prefs['email__enableErrorEmails'] = send_error_emails

        error_email_address = self.pattern_input(
            'Email address to send error messages to [%s]' % school_email,
            message='Invalid email address.',
            pattern='^[^@]+@[^@]+\.[^@]+$',
            default=school_email,
        )
        prefs['email__errorEmailTo'] = error_email_address

        self.stdout.write(
            """
DANCE TYPES
-----------

By default, all class series have both a dance type associated with them, and a class
level associated with that dance type.  To simplify setup, we ask you to define one dance
type, and we also encourage you to set up initial levels.

Remember, you can always rename these initial values or add/delete dance levels later.

            """
        )

        initial_dancetype = self.pattern_input(
            'Name of your initial default dance type [Lindy Hop]',
            message='Invalid dance type name (no special characters)',
            default='Lindy Hop',
        )
        initial_dancetype_object = DanceType.objects.get_or_create(name=initial_dancetype, defaults={'order': 1.0})

        use_initial_levels = self.boolean_input('Use initial levels \'Level 1\', \'Level 2\', and \'Level 3\' [Y/n]', True)
        if use_initial_levels:
            DanceTypeLevel.objects.get_or_create(name='Level 1', danceType=initial_dancetype_object[0], defaults={'order': 1.0})
            DanceTypeLevel.objects.get_or_create(name='Level 2', danceType=initial_dancetype_object[0], defaults={'order': 2.0})
            DanceTypeLevel.objects.get_or_create(name='Level 3', danceType=initial_dancetype_object[0], defaults={'order': 3.0})

        self.stdout.write(
            """

ROLES
-----

Most partnered dance schools define 'Lead' and 'Follow' roles that are used in
the registration process.  If your dance school does not use these roles, or
if you do not ask students to register for a particular role, then answer 'No' below.

            """
        )

        define_roles = self.boolean_input('Define \'Lead\' and \'Follow\' roles [Y/n]: ', True)
        if define_roles:
            DanceRole.objects.get_or_create(name='Lead',defaults={'pluralName': 'Leads', 'order':1.0})
            DanceRole.objects.get_or_create(name='Follow',defaults={'pluralName': 'Follows', 'order': 2.0})
            initial_dancetype_object[0].roles = DanceRole.objects.filter(name__in=['Lead','Follow'])
            initial_dancetype_object[0].save()

        self.stdout.write(
            """
PRICING
-------

All class series are priced by pricing tiers.  A pricing tier defines the default
price for any class series or event associated with that pricing tier.  Default
prices may vary depending on whether the student registers online or at the door,
and default prices may also be different for individuals who receive a student
discount.

If you have enabled the discounts app or the vouchers app, then those discounts or
vouchers are applied relative to the baseline pricing

For example, at Boston Lindy Hop, we charge a default price of $50 for online
registration and $60 for registration at the door.  For college students, we offer
an automatic discount of $10, so prices are $40 and $50, respectively.  Then, we
use the discounts app to provide further discounts for students who register for
more than one class at a time, etc.

Remember, you can always modify, add or delete pricing tiers from the admin
interface after completing this setup.

            """
        )

        initial_pricing_tier_name = self.pattern_input(
            'Give your initial pricing tier a name [Default Pricing]',
            message='Invalid dance type name (no special characters)',
            default='Default Pricing',
        )

        initial_online_price = self.float_input('Initial online price [50]',default=50)
        initial_door_price = self.float_input('Initial at-the-door price [60]',default=60)
        initial_student_online_price = self.float_input('Initial online price for HS/college/university students [40]',default=40)
        initial_student_door_price = self.float_input('Initial at-the-door price for HS/college/university students [50]',default=50)
        initial_dropin_price = self.float_input('Initial price for single-class drop-ins [15]',default=15)

        PricingTier.objects.get_or_create(
            name=initial_pricing_tier_name,
            defaults={
                'onlineGeneralPrice': initial_online_price,
                'doorGeneralPrice': initial_door_price,
                'onlineStudentPrice': initial_student_online_price,
                'doorStudentPrice': initial_student_door_price,
                'dropinPrice': initial_dropin_price,
            })

        if apps.is_installed('danceschool.vouchers'):
            enable_vouchers = self.boolean_input('Enable the voucher/gift certificate system [Y/n]', True)
            prefs['vouchers__enableVouchers'] = enable_vouchers
            prefs['vouchers__enableGiftCertificates'] = enable_vouchers
            prefs['vouchers__enableGiftCertificatePDF'] = enable_vouchers

        if apps.is_installed('danceschool.discounts'):
            enable_discounts = self.boolean_input('Enable the discount system [Y/n]', True)
            prefs['general__discountsEnabled'] = enable_discounts

        if apps.is_installed('danceschool.financial'):
            self.stdout.write(
                """
FINANCIAL MANAGEMENT
--------------------

This project contains a financial app which allows you to manage revenues and expenses
in an automated way. In particular, it is possible for expense items related to instruction
and venue rental to be automatically generated when a series ends, and it is possible for
revenue items related to registrations to be automatically generated as well.  However,
if you do not want these features, then you may disable them below.

If you enable auto-generation of staff expenses, you will also be asked about default
rates of compensation for instructors and other staff.  You may always change these
values by editing the rate in the appropriate Expense Category in the admin interface.

                """
            )

            generate_staff = self.boolean_input('Auto-generate staff expense items for completed events [Y/n]', True)
            prefs['financial__autoGenerateExpensesCompletedEvents'] = generate_staff

            if generate_staff:
                instruction_cat = prefs.get('financial__classInstructionExpenseCat',None)
                if instruction_cat:
                    instruction_cat.defaultRate = self.float_input('Default compensation rate for class instruction [0]',default=0)
                    instruction_cat.save()

                assistant_cat = prefs.get('financial__assistantClassInstructionExpenseCat',None)
                if assistant_cat:
                    assistant_cat.defaultRate = self.float_input('Default compensation rate for assistant instructors [0]',default=0)
                    assistant_cat.save()

                other_cat = prefs.get('financial__otherStaffExpenseCat',None)
                if other_cat:
                    other_cat.defaultRate = self.float_input('Default compensation rate for other event-related staff expenses [0]',default=0)
                    other_cat.save()

            generate_venue = self.boolean_input('Auto-generate hourly venue rental expense items for completed events [Y/n]', True)
            prefs['financial__autoGenerateExpensesVenueRental'] = generate_venue

            generate_registration = self.boolean_input('Auto-generate registration revenue items for registrations [Y/n]', True)
            prefs['financial__autoGenerateRevenueRegistrations'] = generate_registration

        self.stdout.write(
            """
INITIAL PAGES
-------------

The django-danceschool project uses Django CMS, which allows for highly configurable pages
with plugins to display complex functionality.  However, it is often helpful not to have
to start with a completely blank site.  The next few questions will allow you to automatically
set up some of the features that most dance schools use.

Remember, all page settings and content can be changed later via the admin interface.

            """
        )

        try:
            initial_language = settings.LANGUAGES[0][0]
        except IndexError:
            initial_language = getattr(settings, 'LANGUAGE_CODE', 'en')

        add_home_page = self.boolean_input('Create a \'Home\' page [Y/n]', True)
        if add_home_page:
            home_page = create_page('Home', 'cms/home.html', initial_language, menu_title='Home', in_navigation=True, published=True)
            content_placeholder = home_page.placeholders.get(slot='content')
            add_plugin(content_placeholder, 'TextPlugin', initial_language, body='<h1>Welcome to %s</h1>\n\n<p>If you are logged in, click \'Edit Page\' to begin adding content.</p>' % school_name)
            publish_page(home_page, this_user, initial_language)
            self.stdout.write('Home page added.\n')

        add_registration_link = self.boolean_input('Add a link to the Registration page to the main navigation menu [Y/n]', True)
        if add_registration_link:
            registration_link_page = create_page(
                'Registration', 'cms/home.html', initial_language,
                menu_title='Register', slug='register', overwrite_url=reverse('registration'), in_navigation=True, published=True
            )
            self.stdout.write('Registration link added.\n')

        add_instructor_page = self.boolean_input('Add a page to list all instructors with their photos and bios [Y/n]', True)
        if add_instructor_page:
            instructor_page = create_page('Instructors', 'cms/twocolumn_rightsidebar.html', initial_language, menu_title='Instructors', in_navigation=True, published=True)
            content_placeholder = instructor_page.placeholders.get(slot='content')
            sidebar_placeholder = instructor_page.placeholders.get(slot='sidebar')
            add_plugin(
                content_placeholder, 'InstructorListPlugin', initial_language,
                orderChoice=InstructorListPluginModel.OrderChoices.random,
                bioRequired=True,
                template='core/instructor_list.html'
            )
            add_plugin(
                sidebar_placeholder, 'InstructorListPlugin', initial_language,
                orderChoice=InstructorListPluginModel.OrderChoices.random,
                photoRequired=True,
                template='core/instructor_image_set.html'
            )
            publish_page(instructor_page, this_user, initial_language)
            self.stdout.write('Instructor page added.\n')

        add_calendar_page = self.boolean_input('Add a page with a public calendar of classes/events [Y/n]', True)
        if add_calendar_page:
            calendar_page = create_page('Calendar', 'cms/home.html', initial_language, menu_title='Calendar', in_navigation=True, published=True)
            content_placeholder = calendar_page.placeholders.get(slot='content')
            add_plugin(content_placeholder, 'PublicCalendarPlugin', initial_language)
            publish_page(calendar_page, this_user, initial_language)
            self.stdout.write('Calendar page added.\n')

        if apps.is_installed('danceschool.faq'):
            add_faq_page = self.boolean_input('Add an FAQ page and General FAQs Category [Y/n]', True)
            if add_faq_page:
                faq_models = import_module('danceschool.faq.models')
                general_cat = faq_models.FAQCategory.objects.get_or_create(name='General Questions')
                faq_page = create_page('Frequently Asked Questions', 'cms/twocolumn_rightsidebar.html', initial_language, menu_title='FAQ', in_navigation=True, published=True)
                content_placeholder = faq_page.placeholders.get(slot='content')
                sidebar_placeholder = faq_page.placeholders.get(slot='sidebar')
                add_plugin(content_placeholder, 'FAQCategoryPlugin', initial_language, category=general_cat[0])
                add_plugin(sidebar_placeholder, 'FAQTOCPlugin', initial_language)
                publish_page(faq_page, this_user, initial_language)
                self.stdout.write('FAQ page added.\n')

        if apps.is_installed('danceschool.news'):
            add_news_page = self.boolean_input('Add a News page, along with an initial Welcome news item [Y/n]', True)
            if add_news_page:
                news_models = import_module('danceschool.news.models')
                news_models.NewsItem.objects.create(title='Welcome to %s!' % school_name, content='<p>Continue to check this news feed to remain up-to-date on everything that is happening with the school.</p>')

                create_page(
                    'Latest News', 'cms/twocolumn_rightsidebar.html', initial_language,
                    menu_title='News', apphook='NewsApphook', in_navigation=True, published=True)
                self.stdout.write('News page added.\n')

        if apps.is_installed('danceschool.stats'):
            add_stats_page = self.boolean_input('Add a private school stats page and add default graphs [Y/n]', True)
            if add_stats_page:
                stats_page = create_page(
                    'School Performance Stats', 'cms/admin_home.html', initial_language,
                    menu_title='Stats', slug='stats', apphook='StatsApphook', in_navigation=False, published=False)
                sp = StaticPlaceholder.objects.get_or_create(code='stats_graphs')
                stats_placeholder = sp[0].draft
                stats_placeholder_public = sp[0].public

                template_list = [
                    'stats/schoolstats_timeseriesbymonth.html',
                    'stats/schoolstats_averagebyclasstype.html',
                    'stats/schoolstats_averagebyclasstypemonth.html',
                    'stats/schoolstats_cohortretention.html',
                    'stats/schoolstats_averagesbylocation.html',
                    'stats/schoolstats_registrationtypes.html',
                    'stats/schoolstats_referralcounts.html',
                ]
                for template in template_list:
                    add_plugin(stats_placeholder, 'StatsGraphPlugin', initial_language, template=template)
                    add_plugin(stats_placeholder_public, 'StatsGraphPlugin', initial_language, template=template)
                publish_page(stats_page, this_user, initial_language)
                self.stdout.write('School performance stats page added.\n')

        add_login_link = self.boolean_input('Add login/logout and account links to the main navigation bar [Y/n]', True)
        if add_login_link:
            create_page(
                'Login', 'cms/home.html', initial_language,
                menu_title='Login', slug='login', overwrite_url=reverse('account_login'),
                in_navigation=True, limit_visibility_in_menu=VISIBILITY_ANONYMOUS, published=True
            )
            self.stdout.write('Login link added.\n')
            create_page(
                'My Account', 'cms/home.html', initial_language,
                menu_title='My Account', slug='profile', overwrite_url=reverse('accountProfile'),
                in_navigation=True, limit_visibility_in_menu=VISIBILITY_USERS, published=True
            )
            self.stdout.write('\'My Account\' link added.\n')
            create_page(
                'Logout', 'cms/home.html', initial_language,
                menu_title='Logout', slug='logout', overwrite_url=reverse('account_logout'),
                in_navigation=True, limit_visibility_in_menu=VISIBILITY_USERS, published=True
            )
            self.stdout.write('Logout link added.\n')

        if apps.is_installed('danceschool.payments.paypal'):
            add_paypal_paynow = self.boolean_input('Add Paypal Pay Now link to the registration summary view to allow students to pay [Y/n]', True)
            if add_paypal_paynow:
                paynow_sp = StaticPlaceholder.objects.get_or_create(code='registration_payment_placeholder')
                paynow_p_draft = paynow_sp[0].draft
                paynow_p_public = paynow_sp[0].public
                add_plugin(
                    paynow_p_draft, 'CartPaymentFormPlugin', initial_language,
                    successPage=home_page,
                )
                add_plugin(
                    paynow_p_public, 'CartPaymentFormPlugin', initial_language,
                    successPage=home_page,
                )
            self.stdout.write('Paypal Pay Now link added.  You will still need to add Paypal credentials to settings before use.')

        if apps.is_installed('danceschool.payments.stripe'):
            add_stripe_checkout = self.boolean_input('Add Stripe Checkout link to the registration summary view to allow students to pay [Y/n]', True)
            if add_stripe_checkout:
                stripe_sp = StaticPlaceholder.objects.get_or_create(code='registration_payment_placeholder')
                stripe_p_draft = stripe_sp[0].draft
                stripe_p_public = stripe_sp[0].public
                add_plugin(
                    stripe_p_draft, 'StripePaymentFormPlugin', initial_language,
                    successPage=home_page,
                )
                add_plugin(
                    stripe_p_public, 'StripePaymentFormPlugin', initial_language,
                    successPage=home_page,
                )
            self.stdout.write('Stripe checkout link added.  You will still need to add Stripe credentials to settings before use.')

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
                'danceschool.payments.paypal',
                'danceschool.prerequisites',
                'danceschool.private_events',
                'danceschool.stats',
                'danceschool.vouchers'
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
            ]

            for perm in Permission.objects.all():
                if perm.natural_key() in give_explicit:
                    regdesk_group.permissions.add(perm)
            self.stdout.write('Finished creating \'Registration\' group and setting initial permissions.\n')

        # Finished with setup process
        self.stdout.write(self.style.SUCCESS('Successfully setup dance school!  Now enter \'python manage.py runserver\' command to test installation.'))
