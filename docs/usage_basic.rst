Basic Usage
===========

This page provides an overview of some of the key back-end functionality of the project, so that you can get started using the project right away.  Since this project is built on the Django CMS framework, many basic usage tasks are much more thoroughly documented in the `Django CMS documentation <http://docs.django-cms.org/>`_.  It may also be helpful to have an understanding of the Django admin site, which is documented `here <https://docs.djangoproject.com/en/dev/ref/contrib/admin/>`_.

This 


Adding/Editing Pages
--------------------

The Django-danceschool project is built using `Django CMS <http://django-cms.org/>`_, a flexible and highly customizable content management system framework that is built around a system of pages, placeholders, and plugins.  Pages are the basic building block of a website, and each page contains one or more placeholders, which typically correspond to the sections of a page.  Within each placeholder is contained one or more plugin instances, which may be used to provide everything from simple text and images to sophisticated functionality.  Pages exist in a hierarchy, with some pages existing as children of other pages.  By default, Django CMS also adds each page to an automatically-generated menu, and using the included templates, this menu is displayed at the top of the page.

If you are logged in, you will also see another set of menus called the toolbar, with the Django CMS logo on the left and a series of menus and buttons.  The toolbar provides links to most of the day-to-day tasks that a staff user will encounter.  Users only see toolbar links for the tasks for which they have permissions, so if you are not logged in as the superuser, some toolbar items may be unavailable to you.

If you have run the ``setupschool`` script, then several key pages that are commonly used on most dances school websites have already been created for you.  These pages show up in the menu at the top of the page, and can be edited by following the instructions detailed below.

Adding a New Page
^^^^^^^^^^^^^^^^^

The easiest way to add a new page (once you are logged in), is to click the "Create" button on the right-hand side of the CMS toolbar.  You will be given the choice to create either a page at this level of the hierarchy, or a page that is below the current page in the hierarchy.  You will be able to input the page's title, an optional slug (for the URL of the page), and some basic text content.  For simple, static pages with descriptive text, this will often be sufficient.

Editing an Existing Page
^^^^^^^^^^^^^^^^^^^^^^^^

The simplest way to navigate to the page that you wish to edit and click the button to the right of the page that says "Edit page."  Once you have done this, you will be in one of Django CMS's primary edit modes: "Structure" mode or "Content" mode.  You will also see in the toolbar the buttons to toggle between these two modes.

Why two edit modes?  One of the handiest features of Django CMS is "front-end editing.""  That is, you can easily make changes to a page and immediately see what they will look like by making edits while looking directly at the page.  So, for basic text edits, choose "Content" mode.  Then, double-click on the text that you wish to change and proceed to make the edits that you wish.

For more sophisticated changes, such as adding new plugins to the page, you will need to select "Structure" mode.  From here, you can add, delete, and rearrange the plugins within the page to enabled new functionality.

Once you have completed your changes, be sure to click "Publish page changes" in the toolbar to make your changes visible to the public.

Changing the Page's template
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Often, you want different pages of your site to have different layouts to suit their content or functionality.  By changing a page's template, you can quickly modify the layout of a page.  This project ships with basic templates to support single-column and two-column layouts, as well as a plain one-column template without the standard menu that may be used for administrative functions.  You can also create custom templates to enable any layout that you wish.

To change a page's template, enter Edit page mode for the desired page.  Then, select the Page menu within the CMS toolbar, and select a template from the Templates submenu.  Note that depending on the template that you have chosen, your page may now have additional placeholders (places within the page to put plugins).  These will show up in Structure mode.

Note that as with content changes, you will need to publish the page with your template change so that it can be made public.

Unpublishing/Deleting a page
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Enter edit mode for the page in question, and in the Page menu of the toolbar select either "Unpublish page" or "Delete page."

Altering the Page Hierarchy
^^^^^^^^^^^^^^^^^^^^^^^^^^^

To alter the page hierarchy (and other mass functions), select the "Apps" menu within the CMS toolbar, and then select "Pages."  You will see a collapsible page hierarchy displayed, and this will allow you to make changes such as altering the page hierarchy (by dragging and dropping), publishing/unpublishing pages simultaneously, and other changes.

Adding your first Event/Series
------------------------------

Under the "Events" menu, choose "Add a Class Series" or "Add a Public Event" to add an event.  You will be presented with a form to add the series or event and begin taking registrations.  Enter the required information, click "Save," and you're ready to go!  For fields that reference another model within the database (such as Location), you can also use the included "Add" and "Edit" buttons to add/edit existing choices.

FAQs on Adding a Class
----------------------

What's a Class Description/Where Do I Enter The Class Description?
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

It is typical for a class series to be offered multiple times.  To reduce the amount of duplicated effort in setting up each class series, class descriptions are set up to be reusable.  If you have not yet created the class description that you would like, click the "Add" button (plus sign) next to the class description field and create one.

What's a pricing tier/How do I set prices?
""""""""""""""""""""""""""""""""""""""""""

Most classes use a common pricing structure.  Additionally, if you are using the discounts app, it's often desirable to create discounts that apply to only certain types of classes or events.  Therefore, instead of custom per-series pricing, each class or event that has registration requires a Pricing Tier, which defines the base prices for both online registration and at-the-door registration.  There is no limit on the number of tiers, so if you need custom pricing for a specific event for some reason, just create a new pricing tier.

If you haven't yet created any pricing tiers, click the "Add" button (plus sign) next to the pricing tier field and create one.

How do I close a series for registration?
"""""""""""""""""""""""""""""""""""""""""

By default, Series close for registration a number of days after the first occurrence.  This can be set per-event, or it can be set in the site's global settings.  To close a series manually, click "Override Display/Registration/Capacity," and then select a value for "Status" such as "Registration disabled" that closes registration.


How do I hide a series from the registration page?
""""""""""""""""""""""""""""""""""""""""""""""""""

Click "Override Display/Registration/Capacity," and under "Status," choose "Event hidden and registration closed," or one of the other choices that hides the event from the registration page.


Running Registration (and checking in customers)
------------------------------------------------

It is typical at the outset of a dance class series to "check-in" customers, to ensure that they have registered and paid.  This project provides a method for check-in that is straightforward and also mobile-friendly.  To access it, click on the "View Registrations" button in the CMS toolbar.  You will be presented with a list of recent and upcoming class series.  Choose one, and you will see a table with a list of customers who have registered for the class.

The table lists the following:

- The customer's name
- The amount paid for this class.  If discounts or vouchers have been applied, then this will list both a gross (undiscounted) price as well as the net (discounted) price.
- The amount paid this customer's registration.  A customer who registered for multiple classes simultaneously will have the total amount that they owed for the registration listed here.
- Whether the individual indicated that they are a HS/college/university student (in which case you may wish to check their student ID)
- The customer's email address
- The number of classes for which the customer has ever registered

If the user performing checkins has the appropriate permissions, then on the righthand side will also have a series of buttons the link to the items related to the registration, which may be useful for diagnosing non-payment or other technical issues.

If everything in the database is as expected, and if the customer has paid their entire balance for the registration, then the table will appear as normal.  However, in the event of an issues, the price-related cells of the table may be color coded as follows:

- Yellow: Something is wrong or unexpected about this registration.  For example, if the customer has not yet paid, or if a cash payment has not yet been marked as received, then this will show up here.  Or, if the various tables in the database do not match up in some way (e.g. the total reported in the financial app does not match the total on the registration's invoice), then this will show up here.  Use the links at the righthand side of the table to identify the source of the issue.
- Blue: The customer has been refunded a portion of the registration price for either this event, or for another event for which they registered simultaneously.  Typically, this will require no further action.

To mark a customer as checked in, simply check the checkbox on the lefthand side.  When you have finished checking in customers, be sure to click the "Submit Checkins" button at the bottom of the page so that your changes are recorded.

Refunding students
------------------

To refund students in part or in full for a registration, go to "View Registrations" for the event for which the student registered, and click on the "Refund" button on the righthand side of the table.  Enter the amount that you wish to refund, click submit, and click through the confirmation page to process the refund.

If you refund a customer in full for a registration, then that registration will be automatically marked as cancelled, and it will no longer show up in the "View Registrations" page.

Note that automatic refunds depend on the payment processor being used to handle the refund.  The Paypal and Stripe apps that are included with this project do handle automated refunds.


Creating Invoices for Registrations
-----------------------------------

Whenever a customer goes through the registration process, a unique Invoice is automatically generated for that registration.  If the customer pays immediately, then they will typically never see this invoice.  However, it is also possible to submit a registration for a customer such that they will receive a link to the Invoice which they can pay at a later date.

To register a customer and send them an invoice, log in as a user with appropriate permissions to register users at the door, and go to your site's Registration page.  Before selecting the events for which to register them, select the checkbox at the top of the form labeled "This is a door/invoice registration."  Then proceed as normal, entering the customer's information in Step 2 of the registration process.

When you reach the registration summary page in Step 3, you will then see an option at the bottom of the page to send an Invoice to the customer.  Enter their email address, click submit, and they will receive an email inviting them to view and/or pay the invoice.  Once the invoice has been paid, their registration will be automatically processed.

Emailing Students
-----------------

There are many reasons to send mass emails to current or recent students, such as cancellations, class notes, or other announcements.  This project provides a simple way to email recent students.

Under the "Staff" menu on the CMS toolbar, select "Email Students."  On the form, you will be able to select the series and/or recent months for which you would like to email students.  You can enter a custom from address and name, as well as subject and message.  Furthermore, if you have set up custom Email Templates, you can also make use of these to simplify the process of sending common emails.  Note that at this time, the email students form only accepts plain-text emails (i.e. it does not handle HTML email).

Once you are finished, click "Submit," and you will be prompted for a confirmation before your emails are sent.

Substitute Teachers
-------------------

When teachers are unable to teach a scheduled class, it is typical to find another staff member to serve as a substitute.  To simplify the process of keeping track of such substitutes, this project includes a substitute teacher reporting form.

To use the form, choose "Report Substitute Teaching" within the "Staff" menu of the CMS toolbar.  The form will allow you to indicate the specific classes for which one instructor was a substitute for another instructor.  The form does not allow duplicate reports for the same staff member in the same occurrence, so any staff member may fill out the form.  Additionally, the form automatically prevents submissions for events in which the instructors have already been paid, to help prevent overpayment issues.

Class requirements/prerequisites
--------------------------------

If you have installed the ``danceschool.prerequisites`` app, then you have the ability to restrict registration based on whether or not a customer has met certain specified prerequisites.  For example, a customer may be required to have taken a certain number of classes at a lower level before registering for a higher level class.  These requirements can also be enabled in the global settings to be either "hard" (preventing registration entirely) or "soft" (warning the customer before they are permitted to register).  Go to "Registration Requirements/Prerequisites" to manage these prerequisites.

Additionally, some classes, such as audition-only classes, may require explicit permission on a per-customer basis before they can register.  If you have created such a requirement, then customers will be unable to register unless you mark them as able to register.  To this, go to "Customers" under "Related Items" in the "Events" menu, search for the customer using their name or email address, and add a "Customer Requirement" to indicate whether or not they meet a specific requirement.


Measuring School Performance (Stats)
------------------------------------

If you have installed the ``danceschool.stats`` app, then you have access to a range of graphs and information to keep track of your school's performance.  Some of the things that can be automatically tracked include:

- **Monthly performance:** How many registrations does the school get each month, and how many students are in the average class?
- **Cohort retention:**  How many students continue to take classes, vs. how many take only a single class?
- **Performance by class type**
- **Performance by location**
- **Door registrations and student discounts**
- **Marketing referrals:** By linking to special URLs, one can keep track of how many students are registering after clicking on Facebook ads, Google ads, etc.
- **Most active students and teachers**

If you have used the ``setupschool`` script to prepare your project, then all of these graphs should be automatically shown.  Just go to the "Events" menu within the CMS toolbar and select "View School Performance Stats."

Each graph is implemented as a CMS plugin template, so if you have not used the ``setupschool`` script to automatically add all of the graphs to the Stats page, then you will need to add them manually by going to the Stats page and editing the page in Structure mode, then adding plugins.
