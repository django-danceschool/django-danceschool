*****************************
Setup: Email
*****************************

.. _email_setup:

The Django Dance School project is intended to be used with a service that
allows it to send emails.  Some of these emails are automated (e.g.
registration confirmation emails, password reset emails, and event reminders),
while some emails can be sent to groups of customers or staff using built-in online
forms.

Until you set these email settings, you should expect that signing up
new users will return an error, because the app that handles sending
confirmation emails to new users will fail to connect to an email server.

For more details, see the `Django
documentation <https://docs.djangoproject.com/en/dev/topics/email/>`_.

Additionally, because most emails in this project are sent asynchronously,
you will need to run the Huey task queue manager.  If Huey is not running, then
these tasks will be silently queued until Huey is later run.  For production
installations, this is handled automatically.  For development installations,
you will need to type ``python3 manage.py run_huey`` to start Huey and handle
emails.  Your site will continue to handle emails as long as Huey continues to
run.

This page is intended as a quick guide to setting up that email functionality
quickly.  For a more thorough discussion of the way that Django handles
email providers, see the `Django documentation
<https://docs.djangoproject.com/en/1.11/topics/email/>`_.


Development installations
-------------------------

For development installations in which you need to test email functionality,
you will likely need to modify ``settings.py`` to enter the following settings:

- backend: ``EMAIL_BACKEND`` (for SMTP, ``django.core.mail.backends.smtp.EmailBackend``)
- host: ``EMAIL_HOST``
- port: ``EMAIL_PORT``
- username: ``EMAIL_HOST_USER``
- password: ``EMAIL_HOST_PASSWORD``
- use_tls: ``EMAIL_USE_TLS``
- use_ssl: ``EMAIL_USE_SSL``

You are also welcome to implement other email backends, such as SendGrid (described below).

Production installations
------------------------

Although you are welcome to use SMTP or other, the production template has also been
set up for easy email sending through `SendGrid <https://sendgrid.com/>`_, and this
method is highly recommended for its simplicity.  The free tier of SendGrid allows
you to send up to 100 emails per day.

1.  Set up a Sendgrid account at https://sendgrid.com/.  Log into the Sendgrid
    dashboard, then go to Settings > API Keys and click the "Create API Key"
    button to generate a new key for your project's use.  **Be sure that this
    key is kept safe**, since it could allow an unauthorized person to send
    emails on your behalf.
2.  Enter your API key into your production environment
    - For Docker, set the value of ``SENDGRID_API_KEY`` in ``env.default``
    - For Heroku, set ``$SENDGRID_API_KEY`` using the web interface for
      environment variables.
3.  Once you have set the environment variable, you're all done! The project's
    ``settings.py`` will automatically use SendGrid if the environment variable
    is specified.


A Note on Use of Gmail
----------------------

Many users (and schools) have Gmail accounts, and so this is a popular method for sending
emails using Gmail's SMTP server when your site will be sending relatively few emails.
However, there are some special considerations when
using Gmail because of security measures implemented by Google.

Before continuing, set the following in your project's ``settings.py``:

   ::

        EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        EMAIL_HOST = "smtp.gmail.com"
        EMAIL_USE_TLS = True
        EMAIL_PORT = 587
        EMAIL_HOST_USER = "your_account@gmail.com"
        EMAIL_HOST_PASSWORD`` = "your account’s password"

However, these settings alone are insufficient to get Gmail sending to function.  You
must enable "less secure apps" sending functionality, so that Google does not reject
your server's SMTP requests.  For more details, see
`this Google documentation <https://support.google.com/accounts/answer/6010255?hl=en>`_.
