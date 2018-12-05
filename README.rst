Welcome to the Django Dance School project
==========================================

Who is this project for?
------------------------

Partnered social dance schools are complicated. They involve regular classes in multiple configurations which can have prerequisites, auditions, complex pricing, etc. There may also be public events which require registration, and often involve managing instructors, venues, scheduling and finances.

These dance schools are often run by people with limited time and resources. The founders of this project are all Lindy Hoppers, and in this community, even the most prominent and successful dance schools have zero full-time staff. Many schools are unable to grow because they lack the time and resources to manage all of the logistics, whose constraints are a disservice to the dance.

Over several years, `Boston Lindy Hop <https://bostonlindyhop.com/>`__ has sought to address these issues by building a custom registration system with all of the features needed to run a dance school. The commercial options for dance schools are often limited, inflexible, and expensive. This sofware is adaptable enough to be suited to a wide range of dance schools, partnered or otherwise.

The project is designed to be modular and adaptable to the needs to individual dance schools, and can be readily customized while maintaining full integration between the registration system and the public facing parts of the website. Unnecessary features can be turned off, and the entire system is built with a focus on simple usage and customization.

Django Dance School is integrated with `Django CMS <https://www.django-cms.org/en/>`__, which works similarly to other content management systems, making tasks like editing website content easy. Once the website is up and running, it is as straightforward to edit and maintain content as any other CMS. Best of all, this software is free and open source, so you are not stuck paying hefty service fees to a third-party registration provider.

Overview of Features
--------------------

The following are the main features of the project:

-  Class registration (Including conditional pricing)
-  Email management
-  Paypal, Stripe, and Square integration for registration and refunds
-  Instructor scheduling (Including substitutions)
-  Internal scheduling (Private calendars for staff members)
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
-  Private lesson scheduling
-  Basic built-in themes which can be easily customized in the CMS
   without needing to construct your own HTML templates, so that you
   can get started right away!

The following features are in progress:
- Internationalization (ability to translate all site functionality into
other languages)


Installation
------------

Production Deployment (your live site)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For most production deployments and testing, we *strongly* recommend
using the accompanying `production-template
<https://github.com/django-danceschool/production-template/>`__
repository to get your server up and running.  That repository
is designed to use standard tools such as `Docker <https://www.docker.com/>`__
and `Heroku <https://www.heroku.com/>`__ to get you up and running as quickly
as possible, with minimal knowledge of server configuration needed, but with
standard production-level technologies in use.  The exact details of what you
will need will depend on the method of hosting that you choose; learn more in
the `documentation
<https://django-danceschool.readthedocs.io/en/latest/installation_production.html>`__.

Using the installation instructions for `Docker <https://www.docker.com/>`__,
it is also feasible to get a full project server stack running on any machine
(including your local machine for testing).  Although you lose some of the
advantages for rapid development of the Django development server
(such as auto-reload of the server when changes are detected), this method
has the advantage of ensuring that all pieces of your production environment
can be replicated and tested before you deploy your school's website.

Development Installation (for testing and development of custom functionality)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you just want to test out the project locally, work your way
through the code, or develop your own custom templates and functionality using
the Django development server, then this method of installation is for you.

For instructions, see the `Documentation
<https://django-danceschool.readthedocs.io/en/latest/installation_development.html>`__.

History
-------

This project was originally created in Spring-Summer 2010 by Shawn
Hershey, for New School Swing (the predecessor to `Boston Lindy
Hop <https://bostonlindyhop.com/>`__). In March 2015, the project was
taken over by Lee Tucker and Andrew Selzer. Significant contributions
over the course of the project have also been made by Dan Rosenthal,
Jason Swihart, Kevin Sihlanick, and Adam Hitchcock.


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
`issue tracker <https://github.com/django-danceschool/django-danceschool/issues>`_.

Bug fixes, or other contributions that serve the goals of the project may
be submitted as pull requests directly to this repo.

If you wish to extend this project with considerable functionality or major
modifications, please get in touch with Lee and Andrew.

Who do I talk to about additional questions?
--------------------------------------------

-  Lee Tucker: lee.c.tucker@gmail.com
-  Andrew Selzer: apache.danse@gmail.com
