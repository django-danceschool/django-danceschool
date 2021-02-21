Version History
===============

0.9.0 - February 20, 2021
-------------------------

- Complete overhaul of logic underlying the registration system.  Invoices are now focal to the registration process, and price information related to purchases is only stored in the Invoice and its items.
- **New** register app allows for rapid and highly customizable registration workflows for at the door registration and automatic check-in.  (Public-facing instances of the new register app are forthcoming).
- **New** merch app allows for the sale of merchandise at the door, including item variants and basic inventory.
- Significantly improved attendance tracking with occurrence-level event check-ins and occurrence-level tracking of drop-ins.
- Vouchers can now be applied either before or after sales tax is calculated, and can be used on all purchases, not just event registrations.
- Upgraded to Django 3.1, including use of native JSONfield and TextChoices to reduce external dependencies.
- Numerous bug fixes with regard to taxation and refunds.
- Many miscellaneous admin and interface enhancements.

**Note:** This release applies a large number of schema migrations.  It is highly recommended to backup your database before upgrading to 0.9.0.


0.8.6 - April 22, 2019
-------------------------

- **NEW:** Financial performance by date (uses same view as financial performance by month)
- Added ability to submit class registrations via Ajax and receive a JSON response
- Fixed RevenueItem paymentMethod not editable in admin
- Documentation improvements re: emails
- Miscellaneous bug fixes

0.8.5 - April 3, 2019
-------------------------

- Added view for manual generation of repeated financial items, customizable by rule. 
- Fixed event not editable on RevenueItem admin.
- Improved reference links in admin between revenue/expense items, events, and event financial detail views.
- Fixed #139, instance_of reference in EventAutocompleteForm creating issues with initial migration because of content_type reference.
- Re: #140, pinned Huey to version <2.0 to avoid compatibility issues.

0.8.4 - March 22, 2019
-------------------------

- Added EventAutocompleteForm for easier selecting of events in Expense/Revenue reporting forms (#134)
- Improved Revenue Reporting form by adding adjustments/fees and adding ability to mark revenue as received (#135)
- Fixed PublicEvent model showing UTC instead of local time (#136)
- Added direct registration link to PublicEventAdmin (#125)
- Fixed bug that excluded prior-year expenses from financial detail view for events (#137)
- Misc. bug fixes

0.8.3 - March 19, 2019
-------------------------

- Added event-specific financial detail view
- Fixed issue with financial detail view with explicit start/end dates
- Fixed issue with reverse() call when prior site history is missing (e.g. viewing an invoice directly from an email link)
- Fixed extra column with total registrations in finances by event view

0.8.2 - February 24, 2019
-------------------------

- Fixed issue with ExpenseItem changelist form treating payTo as a required field
- Fixed issue with display of most popular vouchers in school stats (#120)
- Fixed access to QuerySet object in core/handlers.py (#121)
- Fixed configuration issue with Redis dependency (#122)
- Fixed issue with reversed occurrence dates in individual series view
- Fixed incorrect page template for staff list in setupschool script (#115)

0.8.1 - January 9, 2019
-----------------------

**NOTE**: To avoid an issue in migrations, it is recommended to upgrade directly to this version or higher and skip
version 0.8.0.

- Fixed issue with financial app migration arising from lack of User and StaffMember methods available in migration.

0.8.0 - January 8, 2019
-----------------------

**NOTE**: The upgrade to version 0.8.0 makes database migrations in the way that financial records are kept that are not designed to be reversed.  It is *strongly* recommended that you backup your site's database immediately before upgrading.

- **NEW**: Pay at the door payment processor app that allows customers to commit to pay at the door, and individuals running registration at the door to rapidly process at-the-door cash payments.
- Substantial under-the-hood improvements to the way in which financial records keep track of transaction parties.
- Month and weekday names now sort logically rather than alphabetically in EventListPlugin as well as registration pages.
- New site-history helper function that improves UX in the admin by redirecting users back to the appropriate previous pages.
- Fixed issues with Square point-of-sale and refund processing callbacks arising from an API change.
- Fixed version incompatibility with Django-easy-pdf (for gift certificates)

0.7.2 - November 20, 2018
-------------------------

- Added default compensation by staff category, with an updated action for resetting/deleting staff member custom compensation.
- Added notes field to manually-added guest list entries.
- fixed EventOccurrence string format issue.
- improvements to EventStaffMemberInline.


0.7.1 - November 13, 2018
-------------------------

- Vouchers can now be restricted to specific series/event categories or sessions (#98)
- Payment processor scripts updated to reflect changed CMS logic (#97)
- Fixed timezone issues with "Duplicate events" view

0.7.0 - November 13, 2018
-------------------------

**NOTE**: After upgrading to 0.7.0, it is recommended to run ``python manage.py setup_permissions`` to ensure that staff have appropriate permissions for the new guestlist app. 

- **New:** Customizable guest lists by individual event, category, or session, with rules for adding staff members.
- Improved management of staff members and instructors in the admin (Instructor is now non-polymorphic).
- Misc. bug fixes and improvements.

0.6.3 - September 21, 2018
--------------------------

- Fixed bug that led EventListPlugin instances to differ between draft and publication.
- Fixed event registration card spacing on mobile.
- Fixed margins on instructor images in Instructor list template.

0.6.2 - September 19, 2018
--------------------------

- **New:** Added short description to Event and submodels.
- Improvements to Event List plugin for greater configurability and filtering.
- Added DJs as a default event staff member category.
- Fixed issues with category-specific templates

0.6.1 - September 18, 2018
--------------------------

- Updated use of Square API to reflect new method of loading access token.

0.6.0 - September 9, 2018
-------------------------

- **New:** Themes app for easier customization of your initial site
  templates.  The project
  now uses the djangocms-bootstrap4 app by default as well, for
  much easier development of sophisticated layouts.
- **New:** Event "sessions" that can be used to group events for
  registration.  The registration page is also much more easily
  reorganized without creating custom templates, by choosing the
  default organization method in registration site settings.
- **New:** Customer groups, to which customers can be easily assigned.
  Both discounts and vouchers may be group-specific as well as customer-
  specific.  And, through an admin action, it is easy to email a group
  of customers all at once.
- **New:** Discounts that apply based on the number of existing registrants,
  including temporary registrants that are still in the registration process.
  This makes it easy to employ popular "First X to register" special pricing.
- Fixed issue with admin template that led many sideframe pages to have
  scrolling disabled (#89)
- Draft FAQs are now properly treated as drafts, and can be published and
  unpublished by admin action (#96 and #95)
- Added dates to refund view for easier processing (#87)
- Fixed discounts not showing up when viewing registrations (#88)
- Removed vestiges of prior Python 2 support


0.5.6 - August 8, 2018
----------------------

- Fixed xhtml2pdf version incompatibility issues.

0.5.5 - April 26, 2018
----------------------

- Fixed banlist module reference issue.

0.5.4 - April 26, 2018
----------------------

- Fixed html5lib version inconsistency issue.
- Fixed missing URLs for djangocmsforms app.
- Simplified README.
- Misc. cleanup


0.5.3 - April 14, 2018
----------------------

- Improved admin listing of expense items.
- Fixed duplicate listing of venue expense items in FinancialDetailView.

0.5.2 - February 21, 2018
-------------------------

- Discounts now show up on the registration cart page, not just the final page (#79)
- Fixed issue with change in name of CKEditor theme (#83)
- Fixed Django 1.11 migration issues with registration template
- Permitted configurable rules for determination of event months


0.5.1 - February 7, 2018
------------------------

- Updated to use Django 1.11 and Django CMS 3.5
- Overhaul and simplification of event templates
- Fixed dependency version issues with Django-dynamic-preferences and django-polymorphic apps
- Misc. bugfixes and linting improvements


0.5.0 - October 3, 2017
-----------------------

- **New:** All templates have been overhauled to use the latest Bootstrap 4 beta.  This will ensure long-term compatibility of your website design.
- **New:** Discounts can now be customer specific, so that they will only be available to certain customers.
- **New:** Additional stats charts are now available, including information on the usage of discounts and vouchers, details regarding time of advance registration, and details on multi-class registrations.
- Improved the templates for stats charts for more consistent formatting using Bootstrap 4 cards.
- Fixed issue with refunding sales tax for complete refunds.
- Fixed issue with footer templates repeating on certain pages.  Footer is now a static placeholder by default for easy editing.
- Registration page templates now use Bootstrap 4 cards for easier themeing and configuration
- Added management tasks for all cron jobs for easier Heroku integration
- Numerous small bug fixes and template improvements.


0.4.1 - Septmeber 19, 2017
--------------------------

- Fixed bug with iCal calendar feed slicing in the core app
- Fixed bug with discount categories that have no applicable discount ordered before discount categories with applicable discount codes
- Fixed template inheritance issue on registration offline template.


0.4.0 - September 14, 2017
--------------------------

- **New:** Square payment processor integration, with the option for both online payments and point-of-sale transactions with a Square card reader.
- **New:** A full private lesson scheduling system, with the ability to either use the default registration and pricing tier system, or the ability to do scheduling only.  Includes notifications for instructors and students, and scheduled lessons automatically show up on the instructor's private internal calendar.
- **New:** More flexible internal calendaring options, including the option to view internal calendars by location and by room
- **New:** The ability to create generic invoices for non-registration items, specify specific invoice recipients, and easily email notification updates to invoice recipients.
- Private events can now specify rooms as well as locations, and will show up on the location/room calendars
- All built-in payment processors now handle sales taxes appropriately (#59)
- On refunds, changes to fees are now allocated across invoiceitems, ensuring that the associated revenue items remain correct (#57)
- Fixed CSRF verification error with Ajax sign-in on the student info page (#58)
- Invoice emails now contain appropriate page protocol in invoice URLs so that they will show up in notification emails as clickable links (#56)
- numerous small bug fixes and improvements

Upgrade notes:
^^^^^^^^^^^^^^

Version 0.4.0 is a fully backwards compatible release.  However, a number of small template changes and improvements have been incorporated on admin and registration templates, so if you are overriding registration templates, you may wish to check that the defaults have not changed.


0.3.0 - September 1, 2017
-------------------------

- **New:** Added discount categories, with the lowest-priced discount *per category* automatically applied as a method of permitting multiple simultaneous discounts.  Categories are orderable so that discounts are always applied in the same order.
- Moved discounted student pricing from the core app to the discounts app.  Core app PricingTiers now contain only onlinePrice, doorPrice, and dropInPrice values.
- Temporary Registration objects now expire and are deleted (along with expired session data) by a Huey cron task (if enabled).  By default, Temporary Registrations expire 15 minutes after the registration process begins, with time extended as they proceed through the process.
- When beginning the registration process, the system looks at both completed registrations and in-process registrations (unexpired TemporaryRegistration instances) to determine if registration is allowed.  This prevents accidental overregistration.
- Fixed issue with the ```settings.py`` provided in the ``default_setup.zip`` file that prevented adding or modidying CMS plugin instances.
- Added separate ``setup_paypal``, ``setup_stripe``, and ``setup_permissions`` commands that can be used separately to handle setup of Paypal, Stripe, and group permissions without running the entire ``setupschool`` management command script.

Upgrade notes:
^^^^^^^^^^^^^^

Because student pricing in the core app has been deleted, individuals upgrading to version 0.3.0 who wish to maintain separate pricing for students will need to create discounts in the discounts app to do so.  All student pricing information will be deleted
when the upgrade takes place.  No existing registrations will be affected by this change.

Upon upgrade, all existing TemporaryRegistration objects will be marked as expired.  If any customers are in the process of registering at the time of upgrade, they will be asked to begin the registration process again.

0.2.4 - August 25, 2017
-----------------------

- **New:** Added a "ban list" app that allows schools to enter a list of names and emails that are not permitted to register, with the option to add photographs and notes.


0.2.3 - August 23, 2017
-----------------------

- **New:** Added the ability to automatically generate "generic" expense items daily/weekly/monthly using
  the same rule-based logic as automatic generation of expenses for locations and staff members.
- Minor admin cleanup in the Financial app.


0.2.2 - August 21, 2017
-----------------------

- Removed hard-coded references to "Lead" and "Follow" roles in certain stats graphs so that they show stats based on all configurable roles.
- Added default ordering to EventOccurrence and other fields to avoid unexpected ordering issues.
- Added the ability to add Events to the registration using a "pre_temporary_registration" signal handler based on
  information collected by the student information form.


0.2.1 - August 16, 2017
-----------------------

- Fixed bug in which adding voucher/discount restrictions caused the changelist admin to fail.


0.2.0 - August 15, 2017
-----------------------

- **New:** Improved automatic generation of expenses for venues and event staff, including flexible options for expenses to be generated per day, per week, or per month for simplified accounting.
- **New:** Locations can now have multiple Rooms, with specified capacities for each.
- **New:** Time-based (early bird) discounts for registration based on the number of days prior to class beginning.
- Series and Event categories can now be flagged for easier separate display on the main Registration page, with easier override of display format for specific categories.
- Through the Customer admin, it is now possible to email specific customers using the standard email form.
- In the prerequisites app, it is now possible to lookup specific customers to determine whether they meet class requirements.
- New options for customer prerequisite items, such as allowing partial simultaneous overlap
- Numerous admin action improvements for easier bulk operations.
- Default installation now uses Huey's SQLite integration for easier setup of development instances
- Improvements to "Add Series" view, now using moment.js and datepair.js
- CMS toolbar menu ordering and display bug fixes
- Numerous admin UI improvements
- Many small bug fixes


0.1.2
-----

- Fixed bug where default navigation menu would not expand on mobile browsers
- Added automatic creation of a Logout link to the default navigation using the setupschool script.


0.1.1
-----

- Fixed bug where email context was not being rendered for HTML emails
- Fixed bug where i18n template tag was not loaded for successful form submission template.

0.1.0
-----

- Initial public release
- Added Stripe Checkout integration
- Updated and simplified payment processor integration
- Added initial tests of basic functionality
