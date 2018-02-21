Version History
===============

0.5.2 - February 21, 2018
-----------------------

- Discounts now show up on the registration cart page, not just the final page (#79)
- Fixed issue with change in name of CKEditor theme (#83)
- Fixed Django 1.11 migration issues with registration template
- Permitted configurable rules for determination of event months


0.5.1 - February 7, 2018
-----------------------

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