************************************************
Manual Project Setup Guide
************************************************

Introduction
^^^^^^^^^^^^


In setting up your project, it is strongly recommended that you deploy
your new project by running the following:

   ::

      django-admin startproject --template http://leetucker.net/django-danceschool/danceschool_default_setup.zip <your_project_name>

However, it is also possible to deploy a new project by manually
editing ``settings.py`` to enter the needed values.

This section describes how to do such an installation.  Keep in mind
that manual installation is only recommended for advanced users who
wish to integrate the danceschool app into a pre-existing Django
installation.  If you are just looking to customize the project, then
you likely want to follow the Development Installation guide.

Importing Third-Party Settings
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Setting up the Django-danceschool project requires setting a large number of
configuration options for third-party apps.  However, these options can be
imported automatically so that you do not need to enter them yourself.
Near the top of the ``settings.py`` file, add the following:

   ::

      from danceschool.default_settings import *

Note also that any of the options specified in ``danceschool.default_settings``
can readily be overridden in ``settings.py``.  Just be sure to set your chosen
setting values *below* the import command above.

Installed Apps
^^^^^^^^^^^^^^

In addition to the various apps that are components of the danceschool project,
there are several other apps that need to be added to your project's ``INSTALLED_APPS``.
It is important to note that the order in which apps are added often matters.
In particular, because Django's template loading and URL pattern matching functions
use the first matching template/pattern, some apps need to be loaded before others
in order for them to function correctly.

First, list the Django CMS app in ``INSTALLED_APPS``, followed by the Django
dynamic preferences app.  These apps go first so that they can find and register
CMS plugins and dynamic preferences from other apps:

   ::
      'cms',
      'dynamic_preferences',

Next, list the core danceschool app, preceded by the themes app.
The core app provides all of the necessary functionality of the project, and is required.
The themes app is optional, but it is highly recommended because it provides the functionality
necessary to enabled the project's built-in themes.

If you have setup any custom app which overrides the templates used by the danceschool project,
then this should also be listed here:

   ::
      # '<your_custom_app>',
      'danceschool.themes',
      'danceschool.core',

The ``danceschool.core`` app contains all of the necessary basic functionality
of the project.  However, depending on your needs, you may want to install some
of all of the following apps by adding them to ``INSTALLED_APPS``:

   ::

      'danceschool.financial',        # Financial reporting and expense/revenue tracking
      'danceschool.private_events',   # Non-public events and calendar with reminders and feeds
      'danceschool.discounts',        # Configurable registration discounts
      'danceschool.vouchers',         # Vouchers, gift certificates, and the referral program
      'danceschool.prerequisites',    # Configurable prerequisites for specific classes
      'danceschool.stats',            # School performance statistics
      'danceschool.news',             # A simple news feed
      'danceschool.faq',              # A simple FAQ system
      'danceschool.payments.paypal',  # Paypal Express Checkout payment processor
      'danceschool.payments.stripe',  # Stripe Checkout payment processor

Then, before including the Django contrib apps, add the following apps (the
order of these does not matter, but some apps *must* be listed before
``django.contrib.admin``):

   ::

      'adminsortable2',
      'allauth',
      'allauth.account',
      'allauth.socialaccount',
      'ckeditor_filebrowser_filer',
      'crispy_forms',
      'dal',
      'dal_select2',
      'daterange_filter',
      'djangocms_admin_style',
      'djangocms_forms',
      'djangocms_text_ckeditor',
      'easy_pdf',
      'easy_thumbnails',
      'filer',
      'huey.contrib.djhuey',
      'menus',
      'polymorphic',
      'sekizai',
      'treebeard',

If you have enabled the ``danceschool.themes`` app, then you will also need:

   ::
      'djangocms_icon',
      'djangocms_link',
      'djangocms_picture',
      'djangocms_bootstrap4',
      'djangocms_bootstrap4.contrib.bootstrap4_alerts',
      'djangocms_bootstrap4.contrib.bootstrap4_badge',
      'djangocms_bootstrap4.contrib.bootstrap4_card',
      'djangocms_bootstrap4.contrib.bootstrap4_carousel',
      'djangocms_bootstrap4.contrib.bootstrap4_collapse',
      'djangocms_bootstrap4.contrib.bootstrap4_content',
      'djangocms_bootstrap4.contrib.bootstrap4_grid',
      'djangocms_bootstrap4.contrib.bootstrap4_jumbotron',
      'djangocms_bootstrap4.contrib.bootstrap4_link',
      'djangocms_bootstrap4.contrib.bootstrap4_listgroup',
      'djangocms_bootstrap4.contrib.bootstrap4_media',
      'djangocms_bootstrap4.contrib.bootstrap4_picture',
      'djangocms_bootstrap4.contrib.bootstrap4_tabs',
      'djangocms_bootstrap4.contrib.bootstrap4_utilities',

Finally, be sure that the following django contrib apps are all listed in
``INSTALLED_APPS`` at the bottom:

   ::

      'django.contrib.auth',
      'django.contrib.contenttypes',
      'django.contrib.sessions',
      'django.contrib.messages',
      'django.contrib.staticfiles',
      'django.contrib.sites',
      'django.contrib.sitemaps',
      'django.contrib.admin',


Template settings
^^^^^^^^^^^^^^^^^
Django CMS requires some specialized context processors to be enabled.  So, add
the following to ``TEMPLATES['OPTIONS']['context_processors']``:

   ::

      'cms.context_processors.cms_settings',
      'sekizai.context_processors.sekizai',
      'danceschool.core.context_processors.site',

Middleware
^^^^^^^^^^

Django CMS requires the following to be added to ``MIDDLEWARE_CLASSES``:

At the top:

   ::

      'cms.middleware.utils.ApphookReloadMiddleware',

Anywhere in MIDDLEWARE_CLASSES:
  
   ::

      'django.middleware.locale.LocaleMiddleware',
      'cms.middleware.user.CurrentUserMiddleware',
      'cms.middleware.page.CurrentPageMiddleware',
      'cms.middleware.toolbar.ToolbarMiddleware',
      'cms.middleware.language.LanguageCookieMiddleware',

Site ID and Language Code
^^^^^^^^^^^^^^^^^^^^^^^^^

Because Django CMS makes use of ``django.contrib.sites``, in order
for a default URL to be available for pages, the CMS needs to know
the database identifier ofyour default site.  For most installations,
this means adding:

   ::

      SITE_ID = 1

Django CMS also uses slightly different language designations than Django
as a whole.  By default, Django's ``settings.py`` ships with
``LANGUAGE_CODE = 'en-us'``.  Assuming that your site will be running in
English, you should change this to ``LANGUAGE_CODE = 'en'``.

URL Handling
^^^^^^^^^^^^

The Danceschool project has a single ``urls.py`` file which handles all
of the URLs for the project and its core dependencies.  Similarly, Django
CMS requires a catch-all URL pattern that tries to match any unmatched
URLs to CMS pages.  So, be sure to add the following code to the bottom
of your ``urls.py``.

   ::

      from django.conf.urls import include, url

      ...


      # Add this at the bottom of urls.py
      urlpatterns += [
          # Include your own app's URLs first to override default app URLs
          # url(r'^', include('<yourapp>.urls')),
          # Now, include default app URLs and CMS URLs
          url(r'^', include('danceschool.urls')),
          url(r'^', include('cms.urls')),
      ]

**Note:** If for any reason you wish to modify any of the default URL paths
provided by the project, you can do so by adding your own URLs prior to the
inclusion of ``danceschool.urls``.

Other Settings You May Wish to Modify
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

As with all Django projects, you are generally free to modify other
settings as you see fit.  However, there are certain other settings
that are commonly modified for each installation, and that you will
likely wish to modify.

For more information on these settings, see the 
`Django documentation <https://docs.djangoproject.com/en/dev/ref/settings/>`_.

**Static file storage/upload settings**:

- ``STATIC_URL`` (set to "/static/" by default)
- ``STATIC_ROOT``
- ``MEDIA_ROOT``
- ``MEDIA_URL``
- ``CKEDITOR_UPLOAD_PATH``

**Django email settings (needed for confirmation emails, etc.)**

For more details on email setup, see the dedicated email setup documentation: :ref:`email_setup`.

- host: ``EMAIL_HOST``
- port: ``EMAIL_PORT``
- username: ``EMAIL_HOST_USER``
- password: ``EMAIL_HOST_PASSWORD``
- use_tls: ``EMAIL_USE_TLS``
- use_ssl: ``EMAIL_USE_SSL``
  
**Django database settings (recommended to change from default SQLite for production applications)**:

- ``DATABASES['default']['ENGINE']``
- ``DATABASES['default']['NAME']``
- ``DATABASES['default']['USER']``
- ``DATABASES['default']['PASSWORD']``
- ``DATABASES['default']['HOST']``
- ``DATABASES['default']['PORT']``

**Django-filer settings**

See the `Django-filer documentation <https://django-filer.readthedocs.io/en/latest/installation.html>`_
for more details:

- ``FILER_STORAGES``
- ``DEFAULT_FILER_SERVERS``
  
** Payment processors **

These are just the settings listed above in :ref:`paypal_setup`, :ref:`stripe_setup`, and :ref:`square_setup`.

For Paypal:

- ``PAYPAL_MODE`` (either "sandbox" or "live")
- ``PAYPAL_CLIENT_ID``
- ``PAYPAL_CLIENT_SECRET``

For Stripe:
- ``STRIPE_PUBLIC_KEY``
- ``STRIPE_PRIVATE_KEY``

For Square:
- ``SQUARE_APPLICATION_ID``
- ``SQUARE_ACCESS_TOKEN``
- ``SQUARE_LOCATION_ID``


.. _huey_setup:

Huey (and Redis) setup for production
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Certain website tasks are best run asynchronously.  For example, when
a student successfully registers for a class, the website does not
need to wait for the confirmation email to be sent in order for the
process to proceed.  Similarly, other tasks such as closing of class
registration are run at regular intervals and do not depend on user
interaction.  For these reasons, this project uses
the `Huey <https://github.com/coleifer/huey>`_ task queue.  Huey is run as
a separate process from your webserver, and when tasks are submitted
to Huey via functions in each app's ``tasks.py``, they are handled by
this separate process.

If you followed the quick start instructions, then Huey is already installed
and a default setup is enabled that will enable you to get going quickly.
On a separate command line from your test server, simply type in 
``python manage.py run_huey`` to run a Huey instance that will handle
sending emails, etc., automatically.  Your site will continue to these
features as well as recurring tasks for as long as this process continues
to run.  

The default settings for Huey involve storing the task queue data in
SQLite-based file storage.  Upon running Huey, you will see a newly
created SQLite file in the same directory as your project's
manage.py file, which stores the task queue data.  Although this approach
allows for convenient setup for testing purposes using the project's
default settings, it is not recommended to use Huey's SQLite storage backend for
production purposes.  Instead, it is strongly recommended that you set up
the popular `Redis <https://redis.io/>`_ cache server, and modify your
``settings.py`` file to use Huey's Redis integration.

Note that These instructions are designed for Linux, and they assume that
you will be running Redis locally using default settings. Getting Redis
running on Windows may require a slightly different process, and
configuring Huey to use a remote Redis installation will also involve
modifying site settings.

1.  Install the Redis client for Python: ``pip install redis``
2.  Start the Redis server: ``sudo service redis-server start``
3.  Add the following to ``settings.py`` (this basic setup can be customized,
    see the `Huey documentation <https://huey.readthedocs.io/en/latest/contrib.html#django>`_).

   ::

      from huey import RedisHuey
      from redis import ConnectionPool
      pool = ConnectionPool(host='localhost', port=6379, max_connections=20)
      HUEY = RedisHuey('danceschool',connection_pool=pool)

4.  As before, run Huey in its own command shell: `python manage.py run_huey`

With these two steps, your installation should now be able to send
emails programmatically, and your site should also run recurring tasks
as long as both Redis and Huey continue to run.
