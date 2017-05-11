from django.core.management.base import BaseCommand
from django.apps import apps
from django.conf import settings
from django.core.urlresolvers import reverse

from danceschool.core.models import DanceType, DanceTypeLevel, DanceRole, PricingTier, InstructorListPluginModel

from dynamic_preferences.registries import global_preferences_registry
import re


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

            try:
                float_result = float(result)
            except ValueError:
                self.stdout.write(self.style.ERROR(message))
                float_result = None
        return float_result

    def handle(self, *args, **options):

        from cms.api import create_page, add_plugin

        # Ensure that we're not evaluating inputs
        if hasattr(__builtins__, 'raw_input'):
            input = __builtins__.raw_input

        # Do some sanity checks to ensure that necessary apps are listed in INSTALLED_APPS
        # before proceeding
        required_apps = [
            ('cms', 'Django CMS'),
            ('danceschoo.core', 'Core danceschool app'),
            ('dynamic_preferences', 'django-dynamic-preferences'),
        ]
        for this_app in required_apps:
            if not apps.is_installed(this_app[0]):
                self.stdout.write(self.style.ERROR('ERROR: %s is not installed or listed in INSTALLED_APPS. Please install before proceeding.' % this_app[1]))
                return None

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

        # School name
        school_name = self.pattern_input(
            'Give your dance school a name [Dance School]',
            message='Invalid school name (no special characters allowed)',
            default='Dance School'
        )
        global_preferences_registry['contact__businessName'] = school_name
        global_preferences_registry['email__defaultEmailName'] = school_name

        # School Email
        school_email = self.patten_input(
            'Provide a default school email address',
            message='Invalid email address.',
            pattern='^[^@]+@[^@]+\.[^@]+$',
        )
        global_preferences_registry['contact__businessEmail'] = school_email
        global_preferences_registry['email__defaultEmailFrom'] = school_email
        global_preferences_registry['email__errorEmailFrom'] = school_email

        # School Phone and Address
        school_phone = input('Provide a phone number for the school (optional): ')
        if school_phone:
            global_preferences_registry['contact__businessPhone'] = school_phone

        school_address1 = input('Enter school street address - Line 1 (optional): ')
        if school_address1:
            global_preferences_registry['contact__businessAddressLineOne'] = school_address1

        school_address2 = input('Enter school street address - Line 2 (optional): ')
        if school_address2:
            global_preferences_registry['contact__businessAddressLineTwo'] = school_address2

        school_city = self.pattern_input(
            'Enter school city [Boston]',
            message='Invalid city (no special characters allowed)',
            pattern='^[a-zA-Z0-9 ]+$',
            default='Boston',
        )
        global_preferences_registry['contact__businessCity'] = school_city

        school_state = self.pattern_input(
            'Enter school state [MA]',
            message='Invalid state (no special characters allowed)',
            pattern='^[a-zA-Z0-9 ]+$',
            default='MA',
        )
        global_preferences_registry['contact__businessState'] = school_state

        school_postal = input('Enter school ZIP/postal code [02114]: ') or '02114'
        global_preferences_registry['contact__businessZip'] = school_postal

        school_country = self.pattern_input(
            'Enter two-letter school country code [US]',
            message='Invalid state (only two uppercase letters allowed)',
            pattern='^[A-Z][A-Z]$',
            default='US',
        )
        global_preferences_registry['contact__businessCountryCode'] = school_country

        currency_code = self.pattern_input(
            'Enter three-letter currency code for transactions [USD]',
            message='Invalid currency code (only three uppercase letters allowed)',
            pattern='^[A-Z][A-Z][A-Z]$',
            default='USD',
        )
        global_preferences_registry['general__currencyCode'] = currency_code

        currency_symbol = input('Unicode currency symbol for display [$]: ') or '$'
        global_preferences_registry['general__currencySymbol'] = currency_symbol

        send_error_emails = self.boolean_input('Send error emails [Y/n]',True)
        global_preferences_registry['email__enableErrorEmails'] = send_error_emails

        error_email_address = self.pattern_input(
            'Email address to send error messages to [%s]' % school_email,
            message='Invalid email address.',
            pattern='^[^@]+@[^@]+\.[^@]+$',
            default=school_email,
        )
        global_preferences_registry['email__errorEmailTo'] = error_email_address

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

        use_initial_levels = self.boolean_input('Use initial levels \'Level 1\', \'Level 2\', and \'Level 3\' [Y]', True)
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

        define_roles = self.boolean_input('Define \'Lead\' and \'Follow\' roles [Y]: ', True)
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

            """
        )

        initial_pricing_tier_name = self.pattern_input(
            'Give your initial pricing tier a name [Default Pricing]',
            message='Invalid dance type name (no special characters)',
            default='Default Pricing',
        )

        initial_online_price = self.float_input('Initial online price [50]',default=50)
        initial_door_price = self.float_input('Initial at-the-door price [60]',default=60)
        initial_student_online_price = self.float_input('Initial online price for college/university students [40]',default=40)
        initial_student_door_price = self.float_input('Initial at-the-door price for college/university students [50]',default=50)

        PricingTier.objects.get_or_create(
            name=initial_pricing_tier_name,
            defaults={
                'onlineGeneralPrice': initial_online_price,
                'doorGeneralPrice': initial_door_price,
                'onlineStudentPrice': initial_student_online_price,
                'doorStudentPrice': initial_student_door_price,
            })

        if apps.is_installed('danceschool.vouchers'):
            enable_vouchers = self.boolean_input('Enable the voucher/gift certificate system [Y/n]', True)
            global_preferences_registry['vouchers__enableVouchers'] = enable_vouchers
            global_preferences_registry['vouchers__enableGiftCertificates'] = enable_vouchers
            global_preferences_registry['vouchers__enableGiftCertificatePDF'] = enable_vouchers

        if apps.is_installed('danceschool.discounts'):
            enable_discounts = self.boolean_input('Enable the discount system [Y/n]', True)
            global_preferences_registry['general__discountsEnabled'] = enable_discounts

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
                """
            )

            generate_staff = self.boolean_input('Auto-generate staff expense items for completed events [Y/n]', True)
            global_preferences_registry['financial__autoGenerateExpensesCompletedEvents'] = generate_staff

            generate_venue = self.boolean_input('Auto-generate venue expense items for completed events [Y/n]', True)
            global_preferences_registry['financial__autoGenerateExpensesVenueRental'] = generate_venue

            generate_registration = self.boolean_input('Auto-generate registration revenue items for registrations [Y/n]', True)
            global_preferences_registry['financial__autoGenerateRevenueRegistrations'] = generate_registration

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
        except:
            initial_language = getattr(settings, 'LANGUAGE_CODE', 'en')

        add_home_page = self.boolean_input('Create a \'Home\' page [Y/n]', True)
        if add_home_page:
            home_page = create_page('Home', 'cms/home.html', initial_language, menu_title='Home', published=True)
            content_placeholder = home_page.placeholders.get(slot='content')
            add_plugin(content_placeholder, 'TextPlugin', initial_language, body='<h1>Welcome to %s</h1>\n\n<p>If you are logged in, click \'Edit Page\' to begin adding content.</p>')
            self.stdout.write('Home page added.\n')

        add_registration_link = self.boolean_input('Add a link to the Registration page to the main navigation menu [Y/n]', True)
        if add_registration_link:
            create_page(
                'Registration', 'cms/home.html', initial_language,
                menu_title='Register', slug='register', overwrite_url=reverse('registration'), published=True
            )
            self.stdout.write('Registration link added.\n')

        add_instructor_page = self.boolean_input('Add a page to list all instructors with their photos and bios [Y/n]', True)
        if add_instructor_page:
            instructor_page = create_page('Instructors', 'cms/twocolumn_rightsidebar.html', initial_language, menu_title='Instructors', published=True)
            content_placeholder = instructor_page.placeholders.get(slot='content')
            sidebar_placeholder = instructor_page.placeholders.get(slot='sidebar')
            add_plugin(
                content_placeholder, 'InstructorListPlugin', initial_language,
                orderChoice=InstructorListPluginModel.OrderChoices.random,
                bioRequired=True,
                template='instructor_list.html'
            )
            add_plugin(
                sidebar_placeholder, 'InstructorListPlugin', initial_language,
                orderChoice=InstructorListPluginModel.OrderChoices.random,
                photoRequired=True,
                template='instructor_image_set.html'
            )
            self.stdout.write('Instructor page added.\n')

        add_calendar_page = self.boolean_input('Add a page with a public calendar of classes/events [Y/n]', True)
        if add_calendar_page:
            calendar_page = create_page('Calendar', 'cms/home.html', initial_language, menu_title='Calendar', published=True)
            content_placeholder = calendar_page.placeholders.get(slot='content')
            add_plugin(content_placeholder, 'PublicCalendarPlugin', initial_language)
            self.stdout.write('Calendar page added.\n')

        if apps.is_installed('danceschool.faq'):
            add_faq_page = self.boolean_input('Add an FAQ page [Y/n]', True)
            if add_faq_page:
                faq_page = create_page('Frequently Asked Questions', 'cms/twocolumn_rightsidebar.html', initial_language, menu_title='FAQ', published=True)
                content_placeholder = faq_page.placeholders.get(slot='content')
                sidebar_placeholder = faq_page.placeholders.get(slot='sidebar')
                add_plugin(content_placeholder, 'FAQCategoryPlugin', initial_language)
                add_plugin(sidebar_placeholder, 'FAQTOCPlugin', initial_language)
                self.stdout.write('FAQ page added.\n')

        if apps.is_installed('danceschool.news'):
            add_news_page = self.boolean_input('Add a News page, along with an initial Weclome news item [Y/n]', True)
            if add_news_page:
                create_page(
                    'Latest News', 'cms/twocolumn_rightsidebar.html', initial_language,
                    menu_title='News', apphook='NewsApphook', published=True)
                self.stdout.write('News page added.\n')

        self.stdout.write(self.style.SUCCESS('Successfully setup dance school.  Use runserver command to test installation.'))
