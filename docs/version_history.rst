Version History
===============


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