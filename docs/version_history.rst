Version History
===============

0.3.0 - September 1, 2017
-----------------------

- **New:** Added discount categories, with the lowest-priced discount *per category* automatically applied as a method of permitting multiple simultaneous discounts.  Categories are orderable so that discounts are always applied in the same order.
- Moved discounted student pricing from the core app to the discounts app.  Core app PricingTiers now contain only onlinePrice, doorPrice, and dropInPrice values.
- Temporary Registration objects now expire and are deleted (along with expired session data) by a Huey cron task (if enabled).  By default, Temporary Registrations expire 15 minutes after the registration process begins, with time extended as they proceed through the process.
- When beginning the registration process, the system looks at both completed registrations and in-process registrations (unexpired TemporaryRegistration instances) to determine if registration is allowed.  This prevents accidental overregistration.
- Fixed issue with the ```settings.py`` provided in the ``default_setup.zip`` file that prevented adding or modidying CMS plugin instances.

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