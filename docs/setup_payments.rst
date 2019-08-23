*************************
Setup: Payment Processors
*************************

.. _setup_payments:

Before you can begin to accept payment for online registrations, you
must set up one or more payment processors.  Luckily, the project
already provides integration with three of the most common payment
processors: Paypal, Stripe, and Square.  This page explains how to enable
these processors for your site's use.

Which Processor Should I Use?
-----------------------------

Choosing a payment processor is a matter of personal preference, of
course.  Your choice may depend on such factors as which processor
you are already using, whose user interface you like most, 

- All three established processors have similar fee structures for
  transactions within the United States.  If you are outside the U.S.,
  check the processor's website for information about availability and
  applicable fees.
- As of 2018, only Square provides a solution for point-of-sale
  integration that works smoothly with mobile web applications such
  as this one.  So, if you wish to take electronic payments for
  full registrations at the door, Square may be the best solution
  for you.
- There is nothing in this project that prevents you from using
  multiple payment processors simultaneously (though of course seeing
  multiple forms might confuse your customers!)


.. _paypal_setup:

Paypal
------

In order to accept and process Paypal payments, you will need to set up
the credentials for your Paypal account.  The Django Dance School
project uses the
`Paypal REST SDK <https://github.com/paypal/PayPal-Python-SDK>`_.
Older versions of this repository used the Paypal IPN system, but this
software is no longer maintained, and it is highly recommended that you
upgrade to using the REST API.

REST API Setup
~~~~~~~~~~~~~~

1. Go to the `Paypal developer website <https://developer.paypal.com/>`_
   and log in using the Paypal account at which you wish to accept
   payments.
2. On the dashboard, under "My Apps & Credentials", find the heading
   for "REST API apps" and click "Create App."  Follow the instructions
   to create an app with a set of API credentials
3. Once you have created an app, you will see credentials listed.  At
   the top of the page, you will see a toggle between "Sandbox" and
   "Live."  If you are setting up this installation for testing only,
   then choose "sandbox" credentials so that you can test transactions
   without using actual money.  For your public installation, use
   "live" credentials.
4. Next steps depend on whether you have performed a production
   installation or a development/manual installation of the project:

- **Development/manual installation**: Edit ``settings.py`` to add:
    -  ``INSTALLED_APPS``: Uncomment/enter ``danceschool.payments.paypal``
    -  ``PAYPAL_MODE``: Either "sandbox" or "live"
    -  ``PAYPAL_CLIENT_ID``: The value of "Client ID"
    -  ``PAYPAL_CLIENT_SECRET``: The value of "Secret".  **Do not share this value 
      with anyone, or store it anywhere that could be publicly accessed**
- **Production template installation**: Instead of modifying ``settings.py``, you 
  can add the values of ``PAYPAL_MODE``, ``PAYPAL_CLIENT_ID``, and 
  ``PAYPAL_CLIENT_SECRET`` as environment variables in the environment where Django 
  operates:
    - For Docker, uncomment and enter the values of ``PAYPAL_MODE``, 
      ``PAYPAL_CLIENT_ID``, and ``PAYPAL_CLIENT_SECRET`` into ``env.default``, 
      using the guidelines above. These values will be loaded into the environment 
      of your Docker container.
    - For Heroku, use the web interface to add the environment variables
        ``PAYPAL_MODE``, ``PAYPAL_CLIENT_ID``, and ``PAYPAL_CLIENT_SECRET``
        using the guidelines above.
    - Once these environment variables are specified, the 
      ``danceschool.payments.paypal`` app will then be automatically enabled.

Adding a Paypal "Pay Now" button to the registration page
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Because this project is designed to be configurable and to accept
different payment providers, the "Pay Now" button is not included by
default on the registration summary page (the last step of the
registration process).  If you have setup your installation by running
the "setupschool" script, and if the ``danceschool.payments.paypal``
app was listed in ``INSTALLED_APPS`` at the time you did so,
then a "Pay Now" button will already be in place.

However, if you have not used the setupschool script, or if you
wish to enable another payment processor after initial setup, then
adding a "Pay Now" button is very straightforward. Follow the steps
for one of these two methods:

Method 1: The Command Line Method (Recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Go to the command line in your project's environment or container
   and type in ``python3 manage.py setup_paypal``.  The setup script
   will check that your configuration variables allow you to connect to
   Paypal, and you will be prompted with the option to add the button
   plugin to the registration summary page.  If the button is
   already present, then it will not add a duplicate.

Method 2: The CMS method
^^^^^^^^^^^^^^^^^^^^^^^^

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

.. _stripe_setup:

Stripe
------

As with Paypal, Stripe integration makes use of a modern API that does
not require you to store any sensitive financial information on your own
server, and it requires only that you enable the app and place your
API keys in your ``settings.py`` file.

Stripe API Setup
~~~~~~~~~~~~~~~~

1.  Go to `Stripe.com <https://www.stripe.com/>`_ and log into your
    account, or sign up for a new account (**Note:** Before running
    transactions in live mode, you will need to activate your account,
    which may involve providing a Tax ID, etc.)
2.  In the dashboard on the left hand side, select "API" to get access
    to your API keys. You will see test credentials, and if your account
    has been activated, you will also see live credentials.  Choose the
    ones that you need.
3. Next steps depend on whether you have performed a production
   installation or a development/manual installation of the project:

   - **Development/manual installation**: Edit ``settings.py`` to add:
     -  ``INSTALLED_APPS``: Uncomment/enter ``danceschool.payments.stripe``
     -  ``STRIPE_PUBLIC_KEY``: Your publishable key.
     -  ``STRIPE_PRIVATE_KEY``: Your secret key.  **Do not share this value with 
       anyone, or store it anywhere that could be publicly accessed**
    - **Production template installation**: Instead of modifying ``settings.py``,
      you can add the values of ``STRIPE_PUBLIC_KEY`` and
      ``STRIPE_PRIVATE_KEY`` as environment variables in the environment
      where Django operates:
      - For Docker, uncomment and enter the values of ``STRIPE_PUBLIC_KEY``
        and ``STRIPE_PRIVATE_KEY`` into
        ``env.default``, using the guidelines above.  These values
        will be loaded into the environment of your Docker container.
      - For Heroku, use the web interface to add the environment variables
        ``STRIPE_PUBLIC_KEY`` and ``STRIPE_PRIVATE_KEY``
        using the guidelnes above.
      - Once these environment variables are specified, the
        ``danceschool.payments.stripe`` app will then be automatically
        enabled.

Adding a Stripe "Checkout Now" button to the registration page
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Because this project is designed to be configurable and to accept
different payment providers, the "Checkout Now" button is not included by
default on the registration summary page (the last step of the
registration process).  If you have setup your installation by running
the "setupschool" script, and if ``danceschool.payments.stripe`` was listed
in ``INSTALLED_APPS`` at the time you did so, then a "Checkout Now" button 
may already be in place.

However, if you have not used the setupschool script, or if you
wish to enable another payment processor after initial setup, then
adding a "Checkout Now" button is very straightforward. Follow the steps
for one of these two methods:

Method 1: The Command Line Method (recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Go to the command line in your project's environment or container and type in
   ``python3 manage.py setup_stripe``.  The setup script will check
   that your configuration variables allow you to connect to
   Stripe, and you will be prompted with the option to add the button
   placeholder on the registration summary page.  If the button is
   already present, then it will not add a duplicate.

Method 2: The CMS method
^^^^^^^^^^^^^^^^^^^^^^^^

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
   this placeholder to add a plugin, and from the "Stripe" section of
   plugins choose "Stripe Checkout Form"
5. Configure the plugin (choose which pages to send customers to when
   they have completed/cancelled payment), and you're all set!

To add a gift certificate form to allow customers to purchase gift
certficates, follow a similar procedure, adding the "Stripe Gift
Certificate Form" plugin to any page of your choosing.

.. _square_setup:

Square
------

You are now able to use the popular Square payment processor in
place of either Paypal or Stripe.  In addition to a standard online
checkout option that is similar to Paypal or Stripe, Square *also*
allows for easy setup of point-of-sale
payments that can be seamlessly integrated with the Django Dance School
system, by allowing your registration person to click a button that sends
them into the Android or iOS point of sale app, with all details loaded,
and by then reporting the results of your transaction back
to your website at a special "callback" URL.  As with the other payment
processors, Square's modern API means that you are not responsible for
the storage of any sensitive financial information.  For these reasons,
Square is a particularly attractive payment option for schools who need
to take payments at the door.

Please note that this project uses version 2 of the Square Connect
APIs.  As of September 2017, this API is only available in certain countries.
Please see 
`the Square documentation <https://docs.connect.squareup.com/articles/faq-international-availability>`_
for more details.

Additionally, please note that *both* the Square point-of-sale integration
and the Square checkout form require that you have HTTPS enabled on your site.
For the checkout form, any page on which the checkout form shows up must be
accessed by HTTPS, or the checkout form will not display.  The checkout form
*will* work on a local test server without HTTPS for testing purposes only.
If you are using the production template on Docker or Heroku, then HTTPS
should be enabled by default.  Setting up HTTPS in other environments is
beyond the scope of this documentation.

Square API Setup
~~~~~~~~~~~~~~~~

1.  Go to `Squarup.com <https://www.squareup.com/>`_ and log into your
    account, or sign up for a new account.  Go to the "Dashboard".
2.  In the dashboard on the left hand side, select "Apps," then select
    the tab for "My Apps", and click to define a new set of app credentials
    that will be used for your website.
3.  From the "My Apps" page, click on "Manage App", and you will see
    the credentials that you need.  If you are only seeking to test online
    payments, then you may opt to use the Sandbox credentials (however,
    be advised that Sandbox credentials cannot be used to test point-of-sale
    payments at this time).
4. Next steps depend on whether you have performed a production
   installation or a development/manual installation of the project:

   - **Development/manual installation**: Edit ``settings.py`` to add:
     -  ``INSTALLED_APPS``: Uncomment/enter ``danceschool.payments.square``
     -  ``SQUARE_APPLICATION_ID``: Your application identifier
     -  ``SQUARE_ACCESS_TOKEN``: Your personal access token.  **Do not share
        this value with anyone, or store it anywhere that could be publicly
        accessed**
     -  ``SQUARE_LOCATION_ID``: The first listed value of Location ID listed
        under "Locations."  Please note that the Danceschool project currently
        does not permit distinguishing among multiple locations in the Square
        payment system.

    - **Production template installation**: Instead of modifying ``settings.py``,
      you can add the values of ``SQUARE_APPLICATION_ID``, ``SQUARE_ACCESS_TOKEN``.
      and ``SQUARE_LOCATION_ID`` as environment variables in the environment
      where Django operates:
      - For Docker, uncomment and enter the values of ``SQUARE_APPLICATION_ID``,
        ``SQUARE_ACCESS_TOKEN``, and ``SQUARE_LOCATION_ID`` into
        ``env.default``, using the guidelines above.  These values
        will be loaded into the environment of your Docker container.
      - For Heroku, use the web interface to add the environment variables
        ``SQUARE_APPLICATION_ID``, ``SQUARE_ACCESS_TOKEN``, and ``SQUARE_LOCATION_ID``
        using the guidelnes above.
      - Once these environment variables are specified, the
        ``danceschool.payments.square`` app will then be automatically
        enabled.
5. **If you intend to use point of sale integration**, you will also need
    to specify a "callback URL," which is the URL that Square's point of sale
    app sends the details of your transaction to after you successfully complete
    it using their app.  To set this URL, from the "Manage App" page on which you
    accessed your API credentials, click on the "Point of Sale API" tab at the top
    of the page.  Then, under "Web," look for an input labeled "Web Callback URLs."
    In this box, enter your callback URL.  If you are using the default URL
    configuration, this URL will be ``https://yourdomain.com/square/process_pointofsale/``.
    However, you can also check to get the exact URL by running ``python3 manage.py setup_square``
    from the command line of your project's environment.


Adding a Square Checkout form and/or point of sale button to the registration page
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Because this project is designed to be configurable and to accept
different payment providers, Square's checkout form and its point-of-sale button are
not included by default on the registration summary page (the last step of the
registration process).  If you have setup your installation by running
the "setupschool" script, and if ``danceschool.payments.square`` was listed
in ``INSTALLED_APPS`` at the time you did so, then a checkout form and/or point of sale button
may already be in place.

However, if you have not used the setupschool script, or if you
wish to enable another payment processor after initial setup, then
adding the form and button are very straightforward. Follow the steps
for one of these two methods:

Method 1: The Command Line Method (recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Go to the command line in your project's environment and type in
   ``python3 manage.py setup_square``.  The setup script will check
   that your configuration variables allow you to connect to
   Square, and you will be prompted with the option to add the checkout form
   plugin and the point of sale button plugin on the registration summary
   page.  If these plugins are already present, then it will not add duplicates.

Method 2: The CMS method
^^^^^^^^^^^^^^^^^^^^^^^^

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
   this placeholder to add a plugin, and from the "Square" section of
   plugins, choose the plugin that you desire.
5. Configure the plugin (choose which pages to send customers to when
   they have completed/cancelled payment), and you're all set!

User Permissions for Square Point of Sale Integration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Unlike with online payment solutions, with point of sale payment, you
do not want most users to see the point of sale button, and you likely
only want it to show up in circumstances where you will be accepting
this type of payment (i.e. at the door).  So, the following restrictions
are in place:

- Only users with the ``square.handle_pos_payments`` permission set can
  see the point of sale button.  Since superusers have all permissions by
  default, you will see the button if you are logged into a superuser account.
  No other users see the button by default, so it is strongly recommended that
  give this permission to the specific Users who run your registration by going to
  *Apps > Users* on the CMS toolbar.
- Only at-the-door registrations (marked as such during step 1 of the registration process)
  see the button, regardless of who the user is that is performing the registration.
- For transactions that take place on a platform other than Android or iOS,
  the point of sale button will display, but it will be disabled and greyed out,
  to reflect the fact that Square point of sale integration only works on Android
  or iOS platforms.
