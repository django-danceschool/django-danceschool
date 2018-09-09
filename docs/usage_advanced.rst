Advanced Usage
==============

Private Events
--------------

If you have enabled the ``danceschool.private_events`` app (enabled in the default setup), then you have the capability to keep track of both publicly scheduled events and class series as well as private events and reminders in a handy calendar view.  This feature is flexibly designed to allow you to keep track of the use of private spaces, schedule of staff meetings, set up to-do reminders, etc.

To access the calendar view, simply go to *Events > School Calendar* on the CMS toolbar.  You will see a calendar with several display options:

- Display all public and private events (default)
- Display only public events
- Display only your personal calendar, including only events for which you are an instructor or other type of staff member.
- Display a calendar of public and private events restricted by location.

Clicking on any event on the calendar will provide you with an option to edit details for that event if you have the permissions to do so, and it will provide a link to the URL for the event if there is one.

The easiest add a new private event is simply to click on the day on which you wish to schedule the event.  You will see options to create repeated events, options to restrict the visibility of the event to only a subset of staff members on your site, and options to send email reminders to yourself or to others about the event.

If you have enabled the private lessons app (described below), then you will also see scheduled private lessons on the private calendar app.  Depending on your user's permissions, you may see only the lessons for which you are scheduled to be an instructor, or you may see all scheduled private lesson events.

Private Lesson Scheduling
-------------------------

If you have enabled the ``danceschool.private_lessons`` app, then you have access to a full private lesson scheduling system.  The private lesson system leverages the same pricing tier structure that is used to price registration for class series and public events. This means that it's easy to set up sophisticated discounts and use vouchers, just like one does for public lesson scheduling.

The ``danceschool.private_lesson`` app is not installed by default, but installation is easy.  Just take the following two steps:

1. In your project's ``settings.py`` file, uncomment the line that lists ``danceschool.private_lessons`` under ``INSTALLED_APPS``. If you do not see this line, then you may add the line yourself after the other danceschool apps that you have enabled are listed.
2. At the command line for your project's environment, run ``python3 manage.py migrate`` to set up the database for private lesson scheduling.

If you enable private lesson scheduling, it is also strongly recommended that you enable the ``danceschool.private_events`` app, so that instructors have calendar access to see the lessons that are scheduled for them.

Configuring Private Lesson Scheduling
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There are several different ways in which studios typically handle private lesson scheduling:

- Full online registration, including online pricing and payment
- Online registration and scheduling, without the option for online payment (for example, if students are asked to pay instructors directly).
- No public registration, only private scheduling (for example, for over-the-phone scheduling only)

The private lesson scheduling system is designed to handle each of these cases seamlessly, although by default it is set up for full online registration.  There are also a number of other useful configuration options.  To set these, go to *Apps > Global Settings* in the CMS toolbar and select the "Private Lessons" section to begin configuration.

Unless you have set up the private lessons app prior to running the ``setupschool`` script, you will also need to add a link to your site's menu to allow customers to access the private lesson scheduling system, and you may also wish to set up permissions for different Users or Groups to access the system appropriately.

Setting up Instructor Availability
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Instructors are not set up to permit private lesson booking for them by default.  Before customers can sign up for private lessons with a particular instructor, three things need to happen:

1. The "Available for private lessons" flag needs to be set on the Instructor's record.  Go to the "Manage Instructors" admin view from the Staff menu of the CMS toolbar, select an instructor, and scroll down to set this flag.
2. Additional "private lesson details" information needs to be specified for the instructor.  These include a default pricing tier for the instructor's lesson slots, the roles for which that instructor is willing to teach lessons, and flags that indicate whether they are available for lessons with couples or small groups.  This information can be set from the same view specified in Step 1 above.
3. Instructor availability slots must be created so that there are specified time slots in which customers can sign up for lessons.

Instructor availability for private lessons is based on slots, which are set by going to *Staff > Private Lesson Availability* in the CMS toolbar.  Depending on your user's permissions, you may have the ability to set availability for each of the school's instructors, or only for yourself.

To add new slots, simply click and drag over the time period in which you would like to create availability slots.  In the pop-up modal, set the initial status for these slots (usually "Available"), and optionally set the pricing and location in which any lesson in that slot will occur.  If you need to set larger blocks of time at once (for example, several hours of availability each day), you may do so from the "month" view of the calendar.  Also, note that if no pricing tier is selected, then customers will not be able to pay for their lesson online; their lesson will simply be scheduled.

All private lesson pricing is per slot.  If you wish to provide pricing for private lessons that is "non-linear" (i.e. with lower per-minute pricing for longer lessons), then the best way to accomplish that is using the discount system.  Generally, the best approach is to create a separate "point group" for private lessons, so that the discounts applied to private lessons may be fully separate from the discounts applied to class series and public events.

Booking Lessons
^^^^^^^^^^^^^^^

For staff users, the booking view can be accessed directly by going to *Staff > Schedule a private lesson* in the CMS toolbar.

Once a private lesson is booked, by default a confirmation email will be sent to both the student and the instructor of the lesson.  If you do not desire the instructor confirmation email to be sent, you may do so from the Private Lessons site preferences.

Once scheduled, private lessons also show up on the instructor's private calendar.

Groups and Permissions
----------------------

Overview
^^^^^^^^

For a more general overview of Django's permissions system, see `The Django Documentation <https://docs.djangoproject.com/en/dev/topics/auth/>`_.

When you installated this project, you created a superuser.  In general, this user automatically has permissions to do anything and everything on the site.  However, for larger schools, there are typically different types of

All permissions in Django may be granted on either a per-user or a per-group basis.  So, for example, if I have two instructors named Alice and Bob, and I want to give them permission to email students, I can either individually give them permissions to email students, or I can create a Group (say, ``Instructors``), make them each members of the group, and then simply give the permission to email students to anyone in that group.

By default, the ``setupchool`` script creates three primary groups, which correspond to a typical stratification of user roles and permissions:

- **Board:** This group is designed for the individuals who manage the school.  By default, the Board group has permissions to do all day-to-day tasks.  For security reasons, a handul of database operations still require the superuser by default, including modifying Groups and permissions.
- **Instructors:**  This group is designed for instructors, who do not need permission to edit most content on the site, but who may run the registration process, submit expenses and revenues, email students, report substitute teaching, etc.
- **Registration Desk:** This group is designed for users who run the registration process (including at-the-door registrations).  By default, these users can do all registration-related tasks except for processing refunds.  In addition, they cannot email students, submit expenses or revenue outside of the normal registration system, or otherwise edit the site's content.

Remember, you can always edit the permissions given to each group (as well as create/delete groups) by logging in as the superuser, going to "Administration" in the apps menu, and then choosing "Groups" under "Authentication and Authorization."

Updating User Permissions on Upgrade
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you have recently upgraded your version of the project to one that has new features, then your users will not automatically be given new permissions to manage those new object.  Fortunately, if you have used the default groups created by the setupschool script, it is easy to keep those permissions up to date.  From a command line in your project's environment, just type ``python3 manage.py setup_permissions``, and all of the default permissions, including any permissions associated with new features, can be granted to the "Board", "Instructors," and "Registration Desk" groups created by the script.  No permissions are removed by this procedure, so any custom permissions that you have set at the User or Group level will not be impacted by doing this.

Detailed List of Permissions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In addition to the permissions automatically generated by Django (add/edit/delete permissions for each Model), this project defines the following permissions which are used to enable/disable various functionality on a per-user basis.

Core app
""""""""

+--------------------------------+--------------------------------------------------------------------------------------------+
| Name                           | Description                                                                                |
+================================+============================================================================================+
| view_staff_directory           | Can access the staff directory view                                                        |
+--------------------------------+--------------------------------------------------------------------------------------------+
| view_school_stats              | Can view statistics about the school's performance.                                        |
+--------------------------------+--------------------------------------------------------------------------------------------+
| update_instructor_bio          | Can update instructors\' bio information                                                   |
+--------------------------------+--------------------------------------------------------------------------------------------+
| view_own_instructor_stats      | Can view one\'s own statistics (if an instructor)                                          |
+--------------------------------+--------------------------------------------------------------------------------------------+
| view_other_instructor_stats    | Can view other instructors\' statistics                                                    |
+--------------------------------+--------------------------------------------------------------------------------------------+
| view_own_instructo_rfinances   | Can view one\'s own financial/payment data (if an instructor)                              |
+--------------------------------+--------------------------------------------------------------------------------------------+
| view_other_instructor_finances | Can view other instructors\' financial/payment data                                        |
+--------------------------------+--------------------------------------------------------------------------------------------+
| report_substitute_teaching     | Can access the substitute teaching reporting form                                          |
+--------------------------------+--------------------------------------------------------------------------------------------+
| can_autocomplete_users         | Able to use customer and User autocomplete features (in various admin forms)               |
+--------------------------------+--------------------------------------------------------------------------------------------+
| view_other_user_profiles       | Able to view other Customer and User profile pages                                         |
+--------------------------------+--------------------------------------------------------------------------------------------+
| view_registration_summary      | Can access the series-level registration summary view                                      |
+--------------------------------+--------------------------------------------------------------------------------------------+
| checkin_customers              | Can check-in customers using the summary view                                              |
+--------------------------------+--------------------------------------------------------------------------------------------+
| accept_door_payments           | Can process door payments in the registration system                                       |
+--------------------------------+--------------------------------------------------------------------------------------------+
| register_dropins               | Can register students for drop-ins.                                                        |
+--------------------------------+--------------------------------------------------------------------------------------------+
| override_register_closed       | Can register students for series/events that are closed for registration by the public     |
+--------------------------------+--------------------------------------------------------------------------------------------+
| override_register_soldout      | Can register students for series/events that are officially sold out                       |
+--------------------------------+--------------------------------------------------------------------------------------------+
| override_register_dropins      | Can register students for drop-ins even if the series does not allow drop-in registration. |
+--------------------------------+--------------------------------------------------------------------------------------------+
| send_email                     | Can send emails using the SendEmailView                                                    |
+--------------------------------+--------------------------------------------------------------------------------------------+
| view_all_invoices              | Can view invoices without passing the validation string.                                   |
+--------------------------------+--------------------------------------------------------------------------------------------+
| send_invoices                  | Can send invoices to students requesting payment                                           |
+--------------------------------+--------------------------------------------------------------------------------------------+
| process_refunds                | Can refund customers for registrations and other invoice payments.                         |
+--------------------------------+--------------------------------------------------------------------------------------------+
| choose_custom_plugin_template  | Can enter a custom plugin template for plugins with selectable template.                   |
+--------------------------------+--------------------------------------------------------------------------------------------+

Financial app

+-----------------------+----------------------------------------------------------+
| Name                  | Description                                              |
+=======================+==========================================================+
| mark_expenses_paid    | Mark expenses as paid at the time of submission          |
+-----------------------+----------------------------------------------------------+
| export_financial_data | Export detailed financial transaction information to CSV |
+-----------------------+----------------------------------------------------------+
| view_finances_bymonth | View school finances month-by-month                      |
+-----------------------+----------------------------------------------------------+
| view_finances_byevent | View school finances by Event                            |
+-----------------------+----------------------------------------------------------+
| view_finances_detail  | View school finances as detailed statement               |
+-----------------------+----------------------------------------------------------+

Prerequisites app

+---------------------+-------------------------------------------------------------------------------+
| Name                | Description                                                                   |
+=====================+===============================================================================+
| ignore_requirements | Can register users for series regardless of any prerequisites or requirements |
+---------------------+-------------------------------------------------------------------------------+

Banlist app

+--------------+-----------------------------------------------+
| Name         | Description                                   |
+==============+===============================================+
| view_banlist | Can view the list of banned individuals.      |
+--------------+-----------------------------------------------+
| ignore_ban   | Can register users despite banned credentials |
+--------------+-----------------------------------------------+



Private lessons app

+--------------------------+----------------------------------------------------------+
| Name                     | Description                                              |
+==========================+==========================================================+
| edit_own_availability    | Can edit one's own private lesson availability.          |
+--------------------------+----------------------------------------------------------+
| edit_others_availability | Can edit other instructors' private lesson availability. |
+--------------------------+----------------------------------------------------------+
| view_others_lessons      | Can view scheduled private lessons for all instructors   |
+--------------------------+----------------------------------------------------------+
