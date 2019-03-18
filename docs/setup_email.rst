*****************************
Setup: Email
*****************************

.. _email_setup:

This page is intended as a quick guide to setting up email functionality
quickly.  For a more thorough discussion of the way that Django handles
email providers, see the `Django documentation
<https://docs.djangoproject.com/en/1.11/topics/email/>`_.

The Django Dance School project is designed for use with a transactional email 
service. Many emails are automated (e.g. registration confirmation emails, password 
reset emails, and event reminders), while manual ones can be sent to groups of 
customers or staff using in-built forms.

Until email settings are configured, users will experience errors related to
emails as the application will be unable to connect to an email service.

Additionally, because most emails in this project are sent asynchronously,
you will need to run the Huey task queue manager.  If Huey is not running, then
these tasks will be silently queued until it is started.  For production
installations, this is handled automatically. For development installations,
you will need to type ``python3 manage.py run_huey`` to start Huey.


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


Production installations
------------------------

The production template for Django-Danceschool has been designed for simple
email configuration through the use of `SendGrid <https://sendgrid.com/>`_ or
`Gmail <https://gmail.com/>`_, the latter of which allows you to send up to 100
emails a day with its free plan, and recommended for its simplicity.

To configure either, edit the file ``env.default`` and scroll down to the
``EMAIL_URL`` parameter. Two examples are provided to configure emails using
Gmail or SendGrid: note that Gmail requires an email address, while SendGrid
instead requests the username associated with an account.

If you decide to use Gmail, you may need to enable the 'Less secure apps'
access for your account so that your SMTP requests are not rejected, which is
explained on `this page 
<https://support.google.com/accounts/answer/6010255?hl=en>`_ of 
Google's support website.
