Installation
============

Basic Installation Process
--------------------------

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
--------------

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
-----------------------------------

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
---------------------------------

In order to accept and process Paypal payments, you will need to set up
the credentials for your Paypal account.  As of version 0.1.0 of this
repository, the Django danceschool project uses the
`Paypal REST SDK <https://github.com/paypal/PayPal-Python-SDK>`.  Older
versions of this repository used the Paypal IPN system, but this
software is no longer maintained, and it is highly recommended that you
upgrade to using the REST API.

REST API Setup
~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
