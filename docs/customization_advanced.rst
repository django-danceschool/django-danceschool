Advanced Customization
======================


Customizing the Registration Form
---------------------------------

Since all danceschools operate somewhat differently, it is common for
schools to wish to collect custom information during the registration
process. By default, this project's registration process proceeds in
three steps:

1. Choose the classes/events that you wish to register for
2. Enter your contact information, any voucher codes that you wish to
   use, etc.
3. Finalize your payment (using Paypal's pay now functions, or by
   submitting information in a door registration)

Most of the time, when a studio wants to customize the information that
they collect, they wish to do so in step 2. So, this project has been
designed to make it relatively easy to do this, using the power of
Python's class inheritance.

Before proceeding, if you are unfamiliar with Django (or with
object-oriented programming), you will need to understand the meaning of
a couple of terms:

-  A *class* is a generic type of object, which you can often think of
   as representing a type of real world object. Classes can contain
   *properties* (e.g. if we had a Dancer class, it could have a property
   ``defaultRoles`` that provides a list of roles that the dancer
   dances, such as "Lead" and "Follow") as well as *methods,* which are,
   in essence, functions within the class that define ways of
   interacting with the class (e.g. our Dancer class could have a method
   ``askToDance()`` that responds with either "Yes" or "No" depending on
   whatever logic we want to implement).
-  An *instance* of a class represents one object within the class. So,
   each dancer in a ballroom might be associated with one instance of a
   Dancer class. Properties are stored for each instance. So, for
   example, one Dancer instance might have only "Follow" in
   ``defaultRoles``, while another might have both "Lead" and "Follow."
-  A *Form* refers to the class which defines which fields are
   displayed, how they are displayed, and how they should be validated.
-  A *View* refers to the class or function which decides what is
   displayed when a request is made, including (for example), the
   displaying of form. In the case of a page displaying a form, it also
   determines what should be done when a form is valid.
-  A *Model* refers to the class which is used to define a specific
   piece of data (like a row in a table representing a Registration, for
   example).

One last very important thing: classes can inherit from other classes.
So, for example, if I wanted to create a DanceCompetitor class, with
properties and methods that are specific to competitors, I wouldn't need
to redefine all of the properties and methods associated with a
DanceCompetitor. I could, instead, have the DanceCompetitor class
inherit those things from the Dancer class. In that case, all
DanceCompetitor instances would also be Dancer instances, while not all
Dancer instances would necessarily be DanceCompetitor instances.

Now that we have that out of the way, here are the steps to customizing
your registration form. These should all be added to your custom
application, and that application must be listed *before* the
``danceschool.core`` app under ``INSTALLED_APPS``.

1. Subclass the RegistrationContactForm (located in
   ``danceschool.core.forms``) to create your own custom form in its
   place.

   The RegistrationContactForm class, like several other forms in this
   project, uses the app django-crispy-forms to make it easier to
   customize functionality and display. So that you do not need to
   re-specify all of the fields in the form, the RegistrationContactForm
   conveniently provided three methods, ``get_top_layout()``,
   ``get_mid_layout()``, and ``get_bottom_layout()``, each of which
   provides a django-crispy-forms Layout object that includes the fields
   in that portion of the form. So, for example, if I want to add a new
   field called "favoriteDancer" to the bottom portion of the form, I
   can simply override the method ``get_bottom_layout()`` as follows:

   ::

           from django import forms
           from danceschool.core.forms import RegistrationContactForm

           class MyCustomForm(RegistrationContactForm):
               favoriteDancer = forms.CharField(label='Name Your Favorite Dancer', required=False)

               def get_bottom_layout():
                   layout = super(MyCustomForm,self).get_bottom_layout()
                   layout.append('favoriteDancer')
                   return layout

   Additional details on working with Django-crispy-forms for form
   customization can be found in its `documentation on
   Layouts <http://django-crispy-forms.readthedocs.io/en/d-0/layouts.html>`__.

2. In your app's ``urls.py``, override the default URL for the view
   ``getStudentView`` to use the newly-created form. For example, if the
   registration contact form is normally found at the url
   /register/getinfo/, then you can add the following to your app's
   ``urls.py``:

   ::

       from django.conf.urls import url
       from danceschool.core.classreg import StudentInfoView
       from .forms import MyCustomForm

       urlpatterns = [ 
           # This should override the existing student info view to use our custom form.
           url(r'^register/getinfo/$', StudentInfoView.as_view(form_class=MyCustomForm), name='getStudentInfo'),
       ]

3. That's it!

But what happens to the data from my custom form field?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In anticipation of the fact that many dance schools need to ask custom
questions at registration time, the TemporaryRegistration and
Registration models have a field called data which can hold arbitrary
form data from the registration process. The contents of the data field
are serialized into a JSON object, so the data are stored as a set of
key-value pairs. By default, any additional data that you collect during
the registration process will be saved to the data field of the
associated TemporaryRegistration. When that customer has completed their
payment, then the data are transferred to the Registration object as
well.

Processing custom fields in the registration form using built-in signals
------------------------------------------------------------------------

When a TemporaryRegistration is created (right before the user is given
options for payment), and when a Registration is finalized after payment
has been processed, the registration system sends a *Signal*, which can
be handled by your own custom signal handlers to do further processing
based on the data.

For example, suppose that you have some mailing list functionality in a
separate app, and when a registration is complete, you want to see
whether they checked the box requesting to be added to the mailing list,
so that you can add them to the mailing list. In your custom app, define
a signal handler that listens for and receives signals from the
``post_registration`` signal. That signal will automatically pass the
finalized registration information to your handler function, and from
there, you can proceed to sign the user up for the mailing list if they
requested it.

For more details on Django signals and signal handlers, see the `Django
documentation <https://docs.djangoproject.com/en/dev/topics/signals/>`__.
