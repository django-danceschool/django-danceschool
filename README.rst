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
-  Paypal Express Checkout integration for registration and refunds
-  Stripe Checkout integration for registration and refunds
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

The following features are in progress:
- Private lesson scheduling
- Internationalization (ability to translate all site functionality into
other languages)

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

-  Python 3.4+
-  The ability to create a virtual environment (on Linux, install the
   ``python-virtualenv`` package)
-  pip - the Python package manager
-  A suitable database. For development and testing, SQLite is used by
   default, so you do not need to do anything to get started.  For production
   uss, it is **strongly Recommended** to use PostgreSQL server 9.4+
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

   ``pip install django-danceschool``

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

      django-admin startproject --template https://raw.githubusercontent.com/django-danceschool/django-danceschool/master/setup/default_setup.zip <your_project_name>

5. Perform initial database migrations

   ::
       
       cd <your_project_name>
       python manage.py migrate

6. Create a superuser so that you can log into the admin interface (you
   will be prompted for username and password)

   ::

       python manage.py createsuperuser

7. **Optional, but strongly recommended:** Run the easy-installer setup
   script, and follow all prompts.  This script will guide you through
   the process of setting initial values for many things, creating a few
   initial pages that many school use, and setting up user groups and
   permissions that will make it easier for you to get started running
   your dance school right away.

   ::

       python manage.py setupschool

8. Run the server and try to log in!

   ::

       python manage.py runserver


Following steps 1-8 above will give you a working installation for testing
purposes.  However, additional steps are needed to setup emails,
payment processor integration, and other automated processes.  For details,
see the Installation page of the documentation.


Contribution guidelines
-----------------------

The goal of this project is to make an extensible code base that can be used
by other dance schools.  We can especially use help with:

- Bug fixes
- Creation and improvement of unit tests
- Documentation improvements
- Planning and implementing any significant new functionality that may be
  valuable to your dance school and also to other schools,

Issues and bugs may be submitted directly to the
`issue tracker <https://github.com/leetucker/django-danceschool/issues>`_.

Bug fixes, or other contributions that serve the goals of the project may
be submitted as pull requests directly to this repo.

If you wish to extend this project with considerable functionality or major
modifications, please get in touch with Lee and Andrew.

Who do I talk to about additional questions?
--------------------------------------------

-  Lee Tucker: lee.c.tucker@gmail.com
-  Andrew Selzer: apache.danse@gmail.com
