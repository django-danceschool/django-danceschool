************************************************
Local Installation for Development
************************************************

This page provides instuctions for a local development installation,
using the provided development template so that you can quickly begin to
explore the project's features locally, and so that you can develop
custom apps and functionality quickly in a local environment.

If you are seeking to deploy a production installation quickly,
this is probably not the right guide for you.  It is strongly recommended
that you check out the production installation guide, which provides
installation instructions for rapid production deployment using
standard tools such as Docker and Heroku.

What you need:
~~~~~~~~~~~~~~

-  Python 3.4, 3.5, or 3.6
-  The ability to create a virtual environment (on Linux, install the
   ``python-virtualenv`` package)
-  pip3 - the Python package manager
-  A suitable database. For development and testing, SQLite is used by
   default, so you do not need to do anything to get started.  For production
   use, it is **strongly Recommended** to use PostgreSQL server 9.4+
-  External library dependencies for Pillow, used for basic image
   processing (see the `Pillow
   Documentation <http://pillow.readthedocs.io/en/3.4.x/installation.html>`__).
-  **Recommended for production use:** `Redis server <https://redis.io/>` for asynchronous handling of emails and other tasks
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
   here <http://andinfinity.de/posts/2014-07-17-quick-note-homebrew-installed-python-fails-to-import-zlib.html>`_.

Basic Installation Process
~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Create a subfolder for your new Django project, and enter it:

   ::

       mkdir django
       cd django

2. Create a new virtual environment and enter it:

   ::

       python3 -m virtualenv .
       source bin/activate

   -  *Note:* Depending on your system, you may need to follow slightly
      modified instructions in order to create a virtual environment. No
      matter which method you use, be sure that your environment is set
      to use Python 3 by default.

3. Install the django-danceschool from `PyPi <https://pypi.python.org/pypi>`_.
   This will also install all of the necessary dependencies (which may take
   awhile)

   ``pip3 install django-danceschool``

   *Note:* Additionally, depending on your operating system, you may
   need to install certain program dependencies in order to install the
   Pillow package and the psycopg2 package (as listed in
   requirements.txt). If you run into issues at this step of the
   installation, look for these issues first.

4. Start your Django project, using the ``django-admin`` command.  To avoid
   having to set a large number of settings manually, we strongly recommend
   that you use the preexisting installation template as follows.  Make sure
   that you are in the folder where you would like your project to be located when you do this.

   ::

      django-admin startproject --template https://github.com/django-danceschool/development-template/archive/master.zip <your_project_name>

5. Perform initial database migrations

   ::
       
       cd <your_project_name>
       python3 manage.py migrate

6. Create a superuser so that you can log into the admin interface (you
   will be prompted for username and password)

   ::

       python3 manage.py createsuperuser

7. **Optional, but strongly recommended:** Run the easy-installer setup
   script, and follow all prompts.  This script will guide you through
   the process of setting initial values for many things, creating a few
   initial pages that many school use, and setting up user groups and
   permissions that will make it easier for you to get started running
   your dance school right away.

   ::

       python3 manage.py setupschool

8. Run the server and try to log in!

   ::

       python3 manage.py runserver


Following steps 1-8 above will give you a working installation for testing
purposes.  However, additional steps are needed to setup emails,
payment processor integration, and other automated processes.
These are described below.


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
   the database using the 
   `django-dynamic-preferences <http://django-dynamic-preferences.readthedocs.io/en/latest/>`_
   app, and then cached)

If you have used the default setup provided in step 4 above, then you have
already been provided with appropriate default settings for a development
instance of the project. For example, Django's debug mode is on, and the
project uses a SQLite backend to store data instead of a production database
such as PostgreSQL.  Before thoroughly testing out the project, the only
settings that you are required so set in ``settings.py`` are for features
such as email and the Paypal/Stripe integration, because these features
cannot be enabled by default until you have entered credentials for those
services. However, before you deploy this project for production purposes,
you will need, *at a minimum*, to customize settings for a payment
processor (e.g. Paypal/Stripe/Square), email, and a production-appropriate
database. Also, often time, if your workflow involves
both a development installation and a production installation, there
will be different settings required for each installation.

For more details on the types of settings that you may need to modify, see
:ref:`manual_settings_list`.  Be sure to also check out the guide to setting
up email, :ref:`setup_email`, the guide to setting up payment processors,
:ref:`setup_payments`, and the guide to the Huey asynchronous task queue,
:ref:`huey_setup`.

Customizing runtime settings is even easier. Simply log in as the
superuser account that you previously created, and go to
http://yoursite/settings/global/. There, you will see organized pages in
which you can change runtime settings associated with various functions
of the site.  If you have run the ``setupschool`` command as instructed
in step 7 above, you will find that sensible defaults for all of the most
important runtime settings have already been put into place for you.
