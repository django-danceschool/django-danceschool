Welcome to the Django Dance School project
==========================================

Who is this project for?
------------------------

Partnered social dance schools are complicated. We run regular class
series in all sorts of different configurations, which may require
prerequisites, auditions, complex pricing, etc. We also often run public
events, some of which require registration, and some of which do not. We
often manage numerous instructors, teach in numerous locations, and have
to manage schedules and finances for all of these things.

At the same time, partnered social dance schools are often run by
amateurs, with limited time and resources. The founders of this project
are all Lindy Hoppers, and in that community, even many of the most
prominent and successful dance schools have zero full-time staff. We
have seen many instances of schools that are simply unable to grow or
expand their reach, because they lack the time and resources to manage
all of the logistical details. Those constraints are a disservice to the
dance.

Over a period of several years, in Boston, we have sought to address
these issues by building our own custom registration system, complete
with all of the features needed to run a sophisticated dance school.
Surprisingly, the commercial options for dance schools are very limited,
inflexible, and often expensive. We ended up with software that suits
our needs well, but that is also adaptable enough to be suited to a wide
range of dance schools, including partnered social dances of all types,
but also to many other types of dance. This project is the result of
those efforts.

The project is designed to be very modular and adaptable to the needs to
individual dance schools. You can readily customize the behavior of your
site to meet your needs, all while maintaining full integration between
your registration system and the public facing portions of the site.
Many features that are not needed can be turned off without affecting
the rest of the site, and the entire system is built with an eye toward
making it easy for individual schools to add custom functionality and
behavior.

The whole thing is integrated with a popular content management system
called `Django CMS <https://www.django-cms.org/en/>`__, that works
similar to other CMS systems that you may be familiar with. That means
that day-to-day tasks like editing website content are easy; once your
site is up and running, it is in most respects as easy to edit and
maintain content as a site built on any other content management
software. Best of all, this software is free and open source, so you are
not stuck paying hefty service fees to a third-party registration
provider for as long as your studio is in operation.

The cost of this flexibility is that getting your site up and running
will take a little bit more work than it would with a paid service. You
will need to run your own copy of this software on a hosted webserver.
You will also need to manually enter a few key site settings before your
site is ready for use, such as email, database, and payment credentials.
Finally, you will probably wish, at a minimum, to create or adopt a
custom template for your site's design, and to integrate those into this
project's content management system (see details below). If you are
unfamiliar with web hosting using Python and Django, then it may be a
good idea to consult a person with the relevant expertise to get your
dance school's website up and running. However, we think that once you
have things running, you will find that the benefits of having your own
system are considerable.

Overview of Features
--------------------

The following are the main features of the project:

-  Class registration (advance online registration and at-the-door
   registration with separate pricing for each)
-  Emailing of registered students
-  Paypal integration for registration and refunds
-  Instructor scheduling
-  Internal scheduling (private internal calendars for all staff
   members)
-  Substitute teaching
-  Expense and revenue reporting
-  Optional automatic generation of expense and revenue line items for
   instructors, substitute teachers, and venues
-  Monthly, annual, and by-series financial summaries
-  Instructor-level financial summaries (for tax purposes)
-  Graphs showing school performance over time as well as breakdowns by
   location, type of class, etc.
-  Discounts
-  Vouchers and gift certificates
-  Configurable customer prerequisites
-  A simple news feed and FAQ system

The following features are in progress: \* Private lesson scheduling \*
Internationalization (ability to translate all site functionality into
other languages) \* Better install scripts and default templates, to
make it even faster to get going.

History
-------

This project was originally created in Spring-Summer 2010 by Shawn
Hershey, for New School Swing (the predecessor to `Boston Lindy
Hop <https://bostonlindyhop.com/>`__). In March 2015, the project was
taken over by Lee Tucker and Andrew Selzer. Significant contributions
over the course of the project have also been made by Dan Rosenthal,
Jason Swihart, and Kevin Sihlanick.

Basic installation
------------------

What you need:
~~~~~~~~~~~~~~

-  Python 3.4+ (code may still run on Python 2.7, but it is untested,
   and the ``requirements.txt`` file works with Python 3 only)
-  The ability to create a virtual environment (on Linux, install the
   ``python-virtualenv`` package)
-  pip - the Python package manager
-  A git client that will allow you to use the command line
-  A suitable database. For development and testing, SQLite is used by
   default. **Strongly Recommended**: PostgreSQL server 9.4+
-  External library dependencies for Pillow, used for basic image
   processing (see the `Pillow
   Documentation <http://pillow.readthedocs.io/en/3.4.x/installation.html>`__).
-  `Redis server <https://redis.io/>` for asynchronous handling of emails and other tasks
-  **For Paypal integration only:** SSL and FFI libraries needed to use the Paypal REST SDK (see `the Github repo <https://github.com/paypal/PayPal-Python-SDK>` for details)

**Linux**

-  If you are using a package manager (such as apt), you can usually
   directly install the needed dependencies for Pillow. For example, on
   Ubuntu:

   ::

       sudo apt-get install libjpeg zlib
       sudo apt-get install redis-server
       sudo apt-get install libssl-dev libffi-dev

**Mac**

-  You'll have to use homebrew to ``brew install`` dependencies above.
   Beware you may run into the zlib issue which can be `answered
   here <http://andinfinity.de/posts/2014-07-17-quick-note-homebrew-installed-python-fails-to-import-zlib.html>`__.

Basic Installation Process
~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Download this repository (you will be
   prompted for username and password)

   ::

       git clone https://github.com/leetucker/django-danceschool

2. Create a subfolder for the project, and enter it:

   ::

       mkdir django
       cd django

3. Create a new virtual environment and enter it:

   ::

       python3 -m virtualenv .
       source bin/activate

   -  *Note:* Depending on your system, you may need to follow slightly
      modified instructions in order to create a virtual environment. No
      matter which method you use, be sure that your environment is set
      to use Python 3 by default.

4. Install the django-danceschool package that you downloaded, which will
   also install all of the necessary dependencies (this may take
   awhile & you may have to use sudo)

   ``pip install /path/to/django-danceschool``

   *Note:* Additionally, depending on your operating system, you may
   need to install certain program dependencies in order to install the
   Pillow package and the psycopg2 package (as listed in
   requirements.txt). If you run into issues at this step of the
   installation, look for these issues first.

5. Start your Django project, using the ``django-admin`` command.  To avoid
   having to set a large number of settings manually, we strongly recommend
   that you use the preexisting installation template as follows.  Make sure
   that you are in the folder where you would like your project to be located when you do this.

   ::

      django-admin startproject --template http://leetucker.net/django-danceschool/danceschool_default_setup.zip <your_project_name>

6. Perform initial database migrations

   ::

       python manage.py migrate

7. Create a superuser so that you can log into the admin interface (you
   will be prompted for username and password)

   ::

       python manage.py createsuperuser

8. **Optional, but strongly recommended:** Run the easy-installer setup
   script, and follow all prompts.  This script will guide you through
   the process of setting initial values for many things, creating a few
   initial pages that many school use, and setting up user groups and
   permissions that will make it easier for you to get started running
   your dance school right away.

   ::

       python manage.py setupschool

9. Run the server and try to log in!

   ::

       python manage.py runserver

Settings Customization and Production Deployment
------------------------------------------------

After performing steps 1-8 above, you should have a working instance of
the danceschool project. However, in order to make the site usable for
your purposes, you will, at a minimum, need to do some basic setting of
settings and preferences

There are two types of settings in this project:

1. Hard-coded settings needed to run the project at all (located in
   settings.py)
2. Runtime settings that customize the site's functionality (stored in
   the database using the django-dynamic-preferences app, and then
   cached)

In order to facilitate the easy deployment of development instances, all
of the default settings for this project are settings that can be used
in a dev instance. For example, debug mode is on, and the server uses a
SQLite backend instead of PostgreSQL. The only exceptions are features
such as email and the Paypal integration, which cannot be enabled by
default until you have entered credentials for those services. However,
before you deploy this project for "production" purposes, you will need,
*at a minimum*, to customize settings for Paypal, email, the database,
and the site's "secret key." Also, often time, if your workflow involves
both a development installation and a production installation, there
will be different settings required for each installation.

The good news is that all of the major settings for this project can be
overridden *without* changing ``settings.py`` directly. Instead, create
a new file, in the same folder as settings.py, called
``settings_local.py``. Anything that you enter in here will
automatically override anything that is entered by default in
settings.py. To get you started, this project includes a file called
``settings_local.example`` which demonstrates how to customize things in
this way. Simply copy ``settings_local.example`` to
``settings_local.py``, modify anything that you need for your local
installation, and you're on your way.

Customizing runtime settings is even easier. Simply log in as the
superuser account that you previously created, and go to
http://yoursite/settings/global/. There, you will see organized pages in
which you can change runtime settings associated with various functions
of the site.  If you have run the ``setupschool`` command as instructed
in step 8 above, you will find that all of the most important runtime
settings have already been put into place for you.

Email Settings
~~~~~~~~~~~~~~

In order for your project to send emails, you need to specify an SMTP
server that will allow you to send those emails, as well as any
credentials needed to log into that server. These settings are contained
in settings.py (and can therefore be changed by defining them in
``settings_local.py``). Look for settings such as ``EMAIL_HOST``,
``EMAIL_HOST_USER``, ``EMAIL_HOST_PASSWORD``, etc.

For more details, see the `Django
documentation <https://docs.djangoproject.com/en/dev/topics/email/>`__.

Additionally, because emails in this project are sent asynchronously,
you will need to setup Redis and Huey as described below.

Redis and Huey setup for production
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Certain website tasks are best run asynchronously.  For example, when
a student successfully registers for a class, the website does not
need to wait for the confirmation email to be sent in order for the
process to proceed.  Similarly, other tasks such as closing of class
registration are run at regular intervals and do not depend on user
interaction.  For these reasons, this project uses a combination of
the `Huey <https://github.com/coleifer/huey>` task queue and the
popular `Redis <https://redis.io/>` cache server.

If you followed the quick start instructions, then Huey and Redis should
both already be installed for you.  However, to get them running so that
your site can send emails, etc., you will need to take a couple of steps.
Note that These instructions are designed for Linux, and they assume that
you will be running Redis locally using default settings. Getting Redis
running on Windows may require a slightly different process, and
configuring Huey to use a remote Redis installation will also involve
modifying site settings.

1.  Start the Redis server: `sudo service redis-server start`
2.  Run Huey in its own command shell: `python manage.py run_huey`

With these two steps, your installation should now be able to send
emails programmatically, and your site should also run recurring tasks
as long as both Redis and Huey continue to run.

Production deployment of Huey is beyond the scope of this documentation.
However, solutions such as `Supervisord <http://supervisord.org/>` are
generally the preferred approach.

Paypal Settings (if using Paypal)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In order to accept and process Paypal payments, you will need to set up
the credentials for your Paypal account.  As of version 0.1.0 of this
repository, the Django danceschool project uses the
`Paypal REST SDK <https://github.com/paypal/PayPal-Python-SDK>`.  Older
versions of this repository used the Paypal IPN system, but this
software is no longer maintained, and it is highly recommended that you
upgrade to using the REST API.

REST API Setup
^^^^^^^^^^^^^^

1. Go to the `Paypal developer website <https://developer.paypal.com/>`
   and log in using the Paypal account at which you wish to accept
   payments
2. On the dashboard, under "My Apps & Credentials", find the heading
   for "REST API apps" and click "Create App."  Follow the instructions
   to create an app with a set of API credentials
3. Once you have created an app, you will see credentials listed.  At
   the top of the page, you will see a toggle between "Sandbox" and
   "Live."  If you are setting up this installation for testing only,
   then choose "sandbox" credentials so that you can test transactions
   without using actual money.  For your public installation, use
   "live" credentials.
4. Edit ``settings_local.py`` to add:
    -  ``PAYPAL_MODE``: Either "sandbox" or "live"
    -  ``PAYPAL_CLIENT_ID``: The value of "Client ID"
    -  ``PAYPAL_CLIENT_SECRET``: The value of "Secret".  **Do not share
    this value with anyone, or store it anywhere that could be publicly
    accessed**


Adding a "Pay Now" button to the registration page
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Because this project is designed to be configurable and to accept
different payment providers, the "Pay Now" button is not included by
default on the registration summary page (the last step of the
registration process).  If you have setup your installation by running
the "setupschool" script, then a "Pay Now" button will already be in
place.

However, if you have not done used the setupschool script, or if you
wish to enable another payment processory, then adding a "Pay Now" 
button is very straightforward. Follow these steps:

1. Log in as a user with appropriate permissions to edit pages and other
   CMS content (the superuser is fine)
2. Proceed through the first two pages of the registration process.
   Entering fake information is fine, as you will not be completing this
   registration.
3. When you get to the registration summary page, click the button in
   the toolbar labeled "Edit Page," then choose "Structure" mode to edit
   the layout of the page.
4. You will see a placeholder for the payment button, called
   "Registration\_Payment\_Placeholder". Click the plus sign (+) next to
   this placeholder to add a plugin, and from the "Paypal" section of
   plugins choose "Paypal Pay Now Form"
5. Configure the plugin (choose which pages to send customers to when
   they have completed/cancelled payment), and you're all set!

To add a gift certificate form to allow customers to purchase gift
certficates, follow a similar procedure, adding the "Paypal Gift
Certificate Form" plugin to any page of your choosing.

Customizing Email Templates
~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, the site sends out a confirmation email whenever a customer
successfully completes their registration and submits payment. It also
sends out a confirmation email when a customer purchases a gift
certificate. The templates for these emails are completely configurable,
and they are stored in the database, so you can customize them without
requiring access to the underlying code.  The first time that you run the
server, the templates are populated with default content using

To edit these email templates (and to create other custom email
templates for your own purposes), simply log in as the superuser (or
another user with appropriate permissions) and go to
http://yoursite/admin/core/emailtemplate/. You will see the templates
listed there, simply click on them and edit as needed.

Note also that these custom email templates are processed much like
standard Django templates, with the exception that some functionality is
disabled for security purposes.

TODO: Explain further.

More Extensive Customization
----------------------------

Custom Templates
~~~~~~~~~~~~~~~~

You will almost certainly want to customize your site's layout and look
somewhat, that means that you will need to add one or more custom
templates to your project. To understand how to adapt custom templates
for your site, you should first understand that Django uses something
called *template inheritance*. That is, if you want to define a specific
template for a specific page, it is generally not necessary to recreate
all of the logic and code to describe the way that the page is laid out.
Rather, you can create a custom template that inherits from another,
more general template, changing only the pieces of the page that differ
from the parent template.

Many templates are also designed not for laying out an entire page, but
for laying out only one section of a page. For example, the navigation
section of a page is often the same across all public-facing pages, but
it may be more convenient to keep the navigation layout in a separate
file and simply use an ``{% include %}`` tag to include it in other
templates as needed. Similarly, CMS plugins that are used to display
pieces of information like lists of upcoming classes or lists of
instructors use templates to describe how that information should be
laid out.

With that in mind, most projects will need to override only a couple of
key templates in order to accomplish the vast majority of customization
desired (all of these templates are located in
``danceschool/core/templates/``):

-  ``cms/home.html``: The base template for all public-facing pages. By
   default, this shows all information in a single column, and all of
   the other templates that are included for public-facing pages
   (``twocolumns_rightsidebar.html`` and
   ``twocolumns_leftsidebar.html``, as well as various other templates)
   inherit from this template.
-  ``cms/navbar.html``: The template that is used to show the navigation
   at the top of the page. By default, this template produces a dropdown
   menu that goes across the top of the page, with two levels of pages
   displayed.
-  ``cms/admin_home.html``: The base template for all private and
   administrative within-site functions, such as the various reporting
   forms and financial summaries. The defaults for this template are
   very plain but also very usable, so you may find that you do not need
   to override this template at all.

All templates can be overridden, but here are a few other templates that
you may wish to consider overriding:

-  ``core/event_registration.html``: The template used for the first
   step of the registration process.
-  ``core/individual_class.html`` and ``core/individual_event.html``:
   The templates used on the automatically-generated pages for each
   class and/or event.
-  ``core/account_profile.html``: The template used for the "customer
   profile" page that is displayed when a customer logs in. If you are
   not allowing customers to sign up or log into the site, then you will
   likely not need to change this template.

Where should I put my custom templates?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When looking for a requested template, Django uses the first template
with the appropriate file name that it encounters. So, when providing
custom templates, there are two places to put them:

1. In a ``templates`` folder within the root folder of your project
2. In the ``templates`` folder of a custom app that is listed in
   INSTALLED\_APPS *before* the original template's app.

Notice also that templates in this project are *namespaced*, meaning
that they are contained within a subfolder with the name of the app for
which they are designed. So, if I have created a new ``cms/home.html``
template, which defines the basic layout for public-facing pages, I can
either save it as ``<BASE_DIR>/templates/cms/home.html``. or I can save
it as ``<BASE_DIR>/my_custom_app/templates/cms/home.html``, where
``my_custom_app`` is the name of an app that has been added to
INSTALLED\_APPS before danceschool.core.

Custom Django CMS Templates
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Django CMS (the content management system that is used to manage most
public-facing pages) allows you to select the appropriate template for
each page. However, not all templates are designed for laying out CMS
pages. By default, the project provides a few CMS-appropriate templates:

-  ``cms/home.html``: For public-facing one-column layouts
-  ``cms/twocolumn_rightsidebar.html``: A two-column layout with a main
   "content" region on the left-hand side and a sidebar on the right.
-  ``cms/twocolumn_leftsidebar.html``: A two-column layout with a main
   "content" region on the right-hand side and a sidebar on the left.
-  ``cms/admin_home.html``: A one-column plain layout for administrative
   functions.

If these templates are insufficient for your needs, you may wish to add
entirely new templates, not just to override preexisting templates. For
example, perhaps you want the front page of your site to be a splash
page, which looks different from the more content-focused pages of your
site. In that case, you will need to do the following:

1. Add your custom template to either the ``templates`` folder of your
   project's root directory, or to the templates folder within a custom
   app.
2. Add the template's filename and a brief description to the setting
   ``CMS_TEMPLATES`` within your project's settings\_local.py
3. Restart the server for your Django project so that the settings are
   reloaded.

Once you have done these steps, you should see your custom template
available as an option for any new or existing pages that you create.

Sources of Templates to Customize
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Although you have complete control over the layout of your site using
custom templates, it is often handy to work from a pre-existing
template. To assist in this process, this project is built using the
popular Bootstrap CSS and Javascript framework. There are many existing
free and paid themes available that are built on the Bootstrap
framework. Here are a couple of sources for these types of templates:

-  `Start Bootstrap <https://startbootstrap.com/>`__
-  `BootstrapMade <https://bootstrapmade.com/>`__
-  `Bootswatch <https://bootswatch.com/>`__

For more details on how to customize templates for use with Django CMS,
see the `Django CMS
Documentation <http://docs.django-cms.org/en/release-3.4.x/introduction/templates_placeholders.html>`__.

For more general information on Django templates, how they work, and how
to customize them, see the `Django
Documentation <https://docs.djangoproject.com/en/dev/topics/templates/>`__.

Customizing the Registration Form (Advanced)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Since all danceschools operate somewhat differently, it is common for
schools to wish to collect custom information during the registration
process. By default, this project's registration process proceeds in
three steps:

1. Choose the classes/events that you wish to register for
2. Enter your contact information, any voucher codes that you wish to
   use, etc.
3. Finalize your payment (using Paypal's pay now functions, or by
   submitting information in a door registration)

Most of the time, when a studio wants to customize the information that
they collect, they wish to do so in step 2. So, this project has been
designed to make it relatively easy to do this, using the power of
Python's class inheritance.

Before proceeding, if you are unfamiliar with Django (or with
object-oriented programming), you will need to understand the meaning of
a couple of terms:

-  A *class* is a generic type of object, which you can often think of
   as representing a type of real world object. Classes can contain
   *properties* (e.g. if we had a Dancer class, it could have a property
   ``defaultRoles`` that provides a list of roles that the dancer
   dances, such as "Lead" and "Follow") as well as *methods,* which are,
   in essence, functions within the class that define ways of
   interacting with the class (e.g. our Dancer class could have a method
   ``askToDance()`` that responds with either "Yes" or "No" depending on
   whatever logic we want to implement).
-  An *instance* of a class represents one object within the class. So,
   each dancer in a ballroom might be associated with one instance of a
   Dancer class. Properties are stored for each instance. So, for
   example, one Dancer instance might have only "Follow" in
   ``defaultRoles``, while another might have both "Lead" and "Follow."
-  A *Form* refers to the class which defines which fields are
   displayed, how they are displayed, and how they should be validated.
-  A *View* refers to the class or function which decides what is
   displayed when a request is made, including (for example), the
   displaying of form. In the case of a page displaying a form, it also
   determines what should be done when a form is valid.
-  A *Model* refers to the class which is used to define a specific
   piece of data (like a row in a table representing a Registration, for
   example).

One last very important thing: classes can inherit from other classes.
So, for example, if I wanted to create a DanceCompetitor class, with
properties and methods that are specific to competitors, I wouldn't need
to redefine all of the properties and methods associated with a
DanceCompetitor. I could, instead, have the DanceCompetitor class
inherit those things from the Dancer class. In that case, all
DanceCompetitor instances would also be Dancer instances, while not all
Dancer instances would necessarily be DanceCompetitor instances.

Now that we have that out of the way, here are the steps to customizing
your registration form. These should all be added to your custom
application, and that application must be listed *before* the
``danceschool.core`` app under ``INSTALLED_APPS``.

1. Subclass the RegistrationContactForm (located in
   ``danceschool.core.forms``) to create your own custom form in its
   place.

   The RegistrationContactForm class, like several other forms in this
   project, uses the app django-crispy-forms to make it easier to
   customize functionality and display. So that you do not need to
   re-specify all of the fields in the form, the RegistrationContactForm
   conveniently provided three methods, ``get_top_layout()``,
   ``get_mid_layout()``, and ``get_bottom_layout()``, each of which
   provides a django-crispy-forms Layout object that includes the fields
   in that portion of the form. So, for example, if I want to add a new
   field called "favoriteDancer" to the bottom portion of the form, I
   can simply override the method ``get_bottom_layout()`` as follows:

   ::

           from django import forms
           from danceschool.core.forms import RegistrationContactForm

           class MyCustomForm(RegistrationContactForm):
               favoriteDancer = forms.CharField(label='Name Your Favorite Dancer', required=False)

               def get_bottom_layout():
                   layout = super(MyCustomForm,self).get_bottom_layout()
                   layout.append('favoriteDancer')
                   return layout

   Additional details on working with Django-crispy-forms for form
   customization can be found in its `documentation on
   Layouts <http://django-crispy-forms.readthedocs.io/en/d-0/layouts.html>`__.

2. In your app's ``urls.py``, override the default URL for the view
   ``getStudentView`` to use the newly-created form. For example, if the
   registration contact form is normally found at the url
   /register/getinfo/, then you can add the following to your app's
   ``urls.py``:

   ::

       from django.conf.urls import url
       from danceschool.core.classreg import StudentInfoView
       from .forms import MyCustomForm

       urlpatterns = [ 
           # This should override the existing student info view to use our custom form.
           url(r'^register/getinfo/$', StudentInfoView.as_view(form_class=MyCustomForm), name='getStudentInfo'),
       ]

3. That's it!

But what happens to the data from my custom form field?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In anticipation of the fact that many dance schools need to ask custom
questions at registration time, the TemporaryRegistration and
Registration models have a field called data which can hold arbitrary
form data from the registration process. The contents of the data field
are serialized into a JSON object, so the data are stored as a set of
key-value pairs. By default, any additional data that you collect during
the registration process will be saved to the data field of the
associated TemporaryRegistration. When that customer has completed their
payment, then the data are transferred to the Registration object as
well.

Processing custom fields in the registration form using built-in signals
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When a TemporaryRegistration is created (right before the user is given
options for payment), and when a Registration is finalized after payment
has been processed, the registration system sends a *Signal*, which can
be handled by your own custom signal handlers to do further processing
based on the data.

For example, suppose that you have some mailing list functionality in a
separate app, and when a registration is complete, you want to see
whether they checked the box requesting to be added to the mailing list,
so that you can add them to the mailing list. In your custom app, define
a signal handler that listens for and receives signals from the
``post_registration`` signal. That signal will automatically pass the
finalized registration information to your handler function, and from
there, you can proceed to sign the user up for the mailing list if they
requested it.

For more details on Django signals and signal handlers, see the `Django
documentation <https://docs.djangoproject.com/en/dev/topics/signals/>`__.

Contribution guidelines
-----------------------

Our long-term goal is to make an extensible code base that can be used
by other dance schools. Bug fixes, or other contributions that serve
that goal, should be submitted directly to this repo. However, if you
wish to extend this project with considerable functionality or major
modifications, please get in touch with Lee and Andrew.

Who do I talk to about additional questions?
--------------------------------------------

-  Lee Tucker: lee.c.tucker@gmail.com
-  Andrew Selzer: apache.danse@gmail.com
