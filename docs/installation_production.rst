*********************
Production Deployment
*********************

If you are looking to immediately using the Django Dance School project as
quickly as possible, then you've come to the right place!  Using the Django
Dance School project's `production template
<https://github.com/django-danceschool/production-template/>`_
repository, you can have a complete installation of the project and all its
dependencies running within minutes.  The production template also
automatically incorporates industry-standard open source tools, so you can
be confident that your site's deployment is stable and secure, and you can
get back to running your school.

**Note:** If you are setting up a Docker or Heroku project for the first time,
it is recommended that you find someone with a background in the use of these
systems to ensure that your deployment goes as smoothly as possible.  If you
encounter errors or missing functionality in setting up this template, please
submit an issue to the issue tracker, or email
`django.danceschool@gmail.com <mailto:django.danceschool@gmail.com>`_.

.. _docker:

Docker
------

`Docker <https://www.docker.com/>`_ is a popular open-source platform for
deployment that is built on the concept of containerization.  Each piece of
your stack (of which the project's Django server is only one) is deployed
inside as separate container, and they interact with one another over an
overlay network that is isolated from regular network traffic.  This makes
Docker stacks easy to configure and reproduce.

To use Docker, you will need access to a server that has both Docker and
Docker Compose installed.  Luckily, it is easy to deploy such a preconfigured
server using popular cloud services such as `DigitalOcean
<https://digitalocean.com/>`_ droplets or Amazon EC2.  The project will run
successfully (and is suitable for most individual schools) on servers with as
little as 1 GB of RAM available, which corresponds to DigitalOcean's smallest
$5/month droplet size.  And, the template can automatically use
LetsEncrypt, so that your site traffic is always automatically SSL encrypted
for free.

Docker can also be deployed on your local machine, allowing you to develop
with a full server stack that is identical to the one you use in production,
even on Windows.  However, for most users, because of the additional
layer of abstraction associated with containerization, use of the development
template (see :ref:`installation_development`_) is still recommended.  See
:ref:`docker_development`_ for more details below.

Docker installation
===================

You Will Need:
- Docker >= 17.12.0
- Docker Compose >= 1.14.0
- Environment that can run Bash scripts (Linux, MacOS, or 
  `Windows 10 WSL
  <https://docs.microsoft.com/en-us/windows/wsl/install-win10>`_)

**Note** These steps assume that you are using the included LetsEncrypt
capabilities for SSL. If you are planning to provide your own SSL certificate,
or you need to use OpenSSL because you are testing on a server that is not
associated with any domain name, you will be prompted for that when you run
the Bash script.

1. On your production server, clone the production template repository:

   ::
      
      git clone https://github.com/django-danceschool/production-template.git

2. Edit the file ``env.web`` to insert value for the following environment variables:
   - ``ALLOWED_HOST``: Your site's domain name (e.g. mydanceschool.com)
   - ``VIRTUAL_HOST``: Your site's domain name
   - ``LETSENCRYPT_HOST``: Your site's domain name
   - ``LETSENCRYPT_EMAIL``: Your email address at which you want to receive error
     notices related to LetsEncrypt.

3. Run the included Docker ``setup-stack.sh`` Bash script.  You will be prompted
   to provide a range of pieces of information that are needed for setup. And,
   as part of the script, you will also be prompted to take the usual steps needed
   for a Django deployment of the project (running initial migrations, collecting
   static files, creating a superuser, and running the ``setupschool`` command to
   initialize the database).

   ::
      
      cd production-template
      docker/setup_stack.sh

4. Use the ``docker`` command to deploy your stack!

   ::

      docker stack deploy -c docker-compose.yml school

Additional Steps/Commands
=========================

- To see that your stack is running, run ``docker ps`` and see that there should
   be 6 different running containers (Gunicorn, Huey, Redis, PostgreSQL, Nginx
   proxy, and LetsEncrypt).
- To remove your stack (stop the server), run ``docker stack rm school``.
- If you modify the ``docker-compose.yml`` file, you will need to re-deploy your
  stack.
- If you modify ``settings.py`` or other Python files (other than custom apps),
  you will need to rebuild the Django container.  The easiest way to do this
  is to run the ``setup_stack.sh`` script again, choosing options to avoid
  overwriting pre-existing credentials, and skipping the setupschool script.

For more information about Docker and how to interact with your Docker stack,
see the `Docker documentation <https://docs.docker.com/>`_.


.. _docker_development:

Developing with Docker
======================

Docker is cross-platform and available for desktops, which means that you can
easily get the production template running on your own machine.  This can be a
great way to test out custom server configurations and/or custom apps. For Linux
and MacOS, just install Docker and follow the steps listed above from the command line.

If you are on Windows, then in order to run the included Bash script, you
will need to install Windows Subsystem for Linux (WSL).

- Follow the instructions from Microsoft: `WSL Installation Guide
  <https://docs.microsoft.com/en-us/windows/wsl/install-win10>`_.
- Once you are on a WSL command line, use the following guide to allow the Linux
  Docker client to connect to your Window's machine's Docker server:
  `Setting Up Docker for Windows and WSL To Work Flawlessly
  <https://nickjanetakis.com/blog/setting-up-docker-for-windows-and-wsl-to-work-flawlessly>`_.

.. _heroku:

Heroku
------

Heroku is a popular platform-as-a-service (PaaS) in which each process in your
school's project runs in a separate container known as a dyno.  Dynos can be
created or destroyed at whim, allowing you to easily scale your project up or
down as needed. However, for most standard dance schools, you will need only
one dyno for each of the following processes:

- Web: The Django instance that serves all web content to users.  By default,
  this dyno serves Django using the popular `Gunicorn <http://gunicorn.org/>`_.
- Worker: The Dance School project uses the `Huey
  <http://huey.readthedocs.io/en/latest/index.html>`_ system to handle
  asynchronous tasks such as sending emails, creating automatically-generated
  expenses, and closing classes for registration depending on elapsed time.
- Redis: Huey's tasks are queued in the Redis data store, which is automatically
  configured by this template.
- Database: This template is set up for Heroku to store all of your data in a
  standard PostgreSQL database which is automatically configured by this template.

Heroku's pricing is based on hours of use for these dynos, as well as their size.
Although Heroku does provide a free tier, with hours of usage limitations, this
tier presents issues for the project because there are numerous tasks that are
required to run at regular intervals (such as creating expense items and closing
classes for registration).  Therefore, we suggest that you use "hobby" dynos.
As of October 2017, hobby web and worker dynos cost $7/month each, a "Hobby
Basic" database dyno costs $9/month, and a hobby Redis dyno is free,
which means that a standard setup that is suitable for most schools will cost
$23/month to host on Heroku.

Initial Heroku Setup
====================

Button-Based Deployment
^^^^^^^^^^^^^^^^^^^^^^^

.. image:: https://www.herokucdn.com/deploy/button.svg
   :target: https://heroku.com/deploy?template=https://github.com/django-danceschool/production-template/tree/master


1. Click the button above and follow the instructions to deploy your app.  This
   will take several minutes.
2. When the initial deployment has finished, click on "Manage App" to open your
   app in the Heroku dashboard.  From there, click the button at the top right
   labeled "More" and select "Run console."  In the field that pops up, type in
   "bash" to access a command line console for your app.
3. At the command-line console, run the following, and follow the prompts at the
   command line to create a superuser and perform your school's initial setup:
   - Create a superuser: ``python manage.py createsuperuser``
   - Setup the school with initial pages and sensible defaults: ``python manage.py setupschool``
4. Type ``exit`` to close the command line process, close out of the console,
   navigate to https://<your-app>.herokuapp.com/ and enjoy!

Manual Method (Recommended for Customization)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You will need:
- A command line Git client installed (you can install one from `here <https://git-scm.com/>`_).
- The Heroku command line client (get it `here <https://devcenter.heroku.com/articles/heroku-cli>`_).
- A Heroku account
- An Amazon AWS account (Heroku dynos cannot store user uploaded files such as instructor photos locally)
- An email address or other method for your site to send emails
- An account with one or more payment processors that you wish to use (Paypal, Square, and Stripe are all supported by default)

1. Open a command line in the location where you would like the local copy of your installation to live.
   Clone this repository to your local folder:

   ``git clone https://github.com/django-danceschool/production-template.git``

2. Login to Heroku:

   ``heroku login``

3. Create a new Heroku app:

   ``heroku create <your-app-name>``

4. Push your project to Heroku, where it will now be deployed (this will take a few minutes the first time that you do it):

   ``git push heroku master``

5. Use one-off dynos to run the initial database migrations that your project needs and to create a
   superuser (you will be prompted for a username and password):

   ::

       heroku run python manage.py migrate
       heroku run python manage.py createsuperuser

6. **Optional, but strongly recommended:** Run the easy-installer setup
   script, and follow all prompts.  This script will guide you through
   the process of setting initial values for many things, creating a few
   initial pages that many school use, and setting up user groups and
   permissions that will make it easier for you to get started running
   your dance school right away.

   ::

       heroku run python manage.py setupschool

7. Go to your site and log in!

Additional Setup Needed
-----------------------

Amazon S3 Setup (Heroku)
========================

Heroku's dynos are not set up to store your user uploaded files permamently.
Therefore, you must set up a third-party storage solution or else your user
uploaded files (instructor photos, receipt attachments for expenses, etc.)
will be regularly deleted.

To enable file upload to Amazon S3, you will first need to create an S3 bucket,
with access permissions set so that uploaded files can be publicly read.  Then,
in order for Heroku to access S3, you must set all of the following environment
variables:
- ``AWS_ACCESS_KEY_ID``
- ``AWS_SECRET_ACCESS_KEY``
- ``AWS_STORAGE_BUCKET_NAME``

Once these settings have been set, Amazon S3 upload of your files should be
automatically enabled!

Payment Processor Setup
=======================

This installation is configured to read your payment processor details from
environment variables.  If you have added the appropriate payment processor
details needed for the three standard payment processors, then the appropriate
payment processor app will automatically be added to ``INSTALLED_APPS``, so
that you do not need to edit the settings file at all in order to begin
accepting payments.

For details on how to get the credentials that you will need for each payment
processor, see: :ref:`setup_payments`_.

Email Setup
===========

Your project needs a way to send emails, so that new registrants will be
notified when they register, so that you can email your students, so that
private event reminder emails can be sent, etc.

By default, this installation uses the ``dj-email-url`` app for simplified
email configuration.  You can specify a simple email URL that will permit
you to use standard services such as Gmail.  This installation template also
has built-in functionality for the popular `Sendgrid <https://sendgrid.com/>`_
email system.  For most small dance schools, the Sendgrid free tier is
adequate to send all school-related emails, but Sendgrid allows larger volume
emailing as well.

Examples
^^^^^^^^

- **Sendgrid:** set ``$SENDGRID_API_KEY`` to your SendGrid API key, set
  ``$SENDGRID_USERNAME`` to your SendGrid username and set ``$SENDGRID_PASSWORD`` to your SendGrid password.  SendGrid will then be enabled as your email service automatically.
- **Gmail:** set ``$EMAIL_URL`` to 'smtps://user@domain.com:pass@smtp.gmail.com:587'.
  Note that Gmail allows only approximately 100-150 emails per day to be sent from a
  remote email client such as your project installation.
