Basic Customization
===================

Customizing Email Templates
---------------------------

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


Customizing Page Templates
--------------------------

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
   ``CMS_TEMPLATES`` within your project's settings.py
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
Documentation <https://docs.djangoproject.com/en/dev/topics/templates/>`_.
