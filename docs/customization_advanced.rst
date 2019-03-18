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

Adding a Custom Payment Processor
---------------------------------

The danceschool project supports two of the most popular online payment
processors (Paypal and Stripe).  It also contains basic functionality
for keeping track of cash payments.  However, depending on your location,
you may want or need to accept online payments from other payment processors.

Since payment processors vary in the way that they handle transactions from
websites, this documentation cannot provide comprehensive instructions.
However, this document provides a starting point for understanding how to
implement a custom payment processor.  If you are attempting to do this,
it is highly recommended to look at the code for the existing payment processor
apps, ``danceschool.payments.paypal`` and ``danceschool.payments.stripe``, to
see how they work.

The PaymentRecord Model
^^^^^^^^^^^^^^^^^^^^^^^

The ``danceschool.core`` app provides a PaymentRecord model that is designed
to be a polymorphic model using the
`Django-polymorphic <http://django-polymorphic.readthedocs.io/en/stable/>`
app.  It provides several key fields that are common to all payment
processors:

- A foreign key relationship to the Invoice model (since payments are
  associated with invoices).
- Creation date and modification date fields
- Several methods and descriptive properties that may need to be overridden
  on a per-payment processor basis, such as the ``refundable`` property
  to indicate whether a payment is refundable, and the ``refund()`` method
  to actually process a refund.

To create a new payment processor, first create a new model in your app's
``models.py`` that simply subclasses the ``danceschool.core.models.PaymentRecord`` model.
Because of the way Django-polymorphic works, your payments will now be recognized just as
payments from other payment processors.

Add any fields that your particular payment processor may need (for example some kind of
transaction identifier field).  Then, be sure to override the following from the parent model:

- The ``refundable`` property (decorated method): defaults to False. This can 
  usually just return True if your payment method is refundable.
- The ``recordId`` property (decorated method).  This will usually just return the identifier used by the payment
  processor, but since different payment processor apps must store this information differently, ``recordId``
  ensures that the information is always available to the parent app.
- The ``methodName`` property (decorated method).  This just returns a readble name for the type of payment processor
  used, such as "Paypal Express Checkout" or "Stripe Checkout."
- The ``netAmountPaid`` property (decorated method).  This should return the amount that was paid *net of any refunds*.
- The ``refund()`` method.  If your API allows refunds of transactions, this should be handled here.  An ``amount``
  parameter should be accepted to permit partial refunds.
- The ``getPayerEmail()`` method.  This method should return the email address of the person who paid, in case they
  need to be contacted.  Many payment processors store this information automatically, but if yours does not, then
  you can potentially create a model field to store it.

Payment Processor Views
^^^^^^^^^^^^^^^^^^^^^^^

Your payment processor will need to define a view that receives data from the processor's website.  The view
also needs to do the following:

1.  Determine whether a payment is being made on a Temporary Registration or an existing Invoice.
2.  If a payment is being made on a Temporary Registration, then it needs to create a new Invoice using
    the ``get_or_create_from_registration()`` class method of the Invoice class.
3.  If the payment is successful, then your view should call the ``processPayment()`` method of the associated
    invoice to record that the payment has been made.  The ``processPayment()`` method will handle finalizing
    the registration if applicable, sending the appropriate email notifications, etc.
4.  Your view will either need to return an ``HttpResponseRedirect()`` to an appropriate success URL, or your
    plugin template will need to use Javascript to redirect the user after a successul payment is made
    (or notify the user if a payment is unsuccessful).
5.  Additional steps may be necessary if you intend to use your payment processor to allow customers to
    purchase gift certificates (as the Paypal and Stripe apps allow).
    

It is highly recommended that you follow along with the ``views.py`` of the existing payment processors to 
be sure that you follow the appropriate steps.

Creating a CMS Plugin
^^^^^^^^^^^^^^^^^^^^^

To add a checkout button for your payment processor, you will need to create a CMS plugin that can
be added to the page Placeholder where checkout happens.  To do this, create a file in your app called
``cms_plugins.py``, and define a new plugin here as a class that inherits from ``cms.plugin_base.CMSPluginBase``.
Within the plugin class, specify template the contains whatever is needed for your payment processor, and use
a custom ``render()`` method to add any additional context data that may be needed for your page.

The existing payment processor apps are a good resource for understanding how to implement one of these plugins.
It is also a good idea to read the `Django CMS documentation
<http://docs.django-cms.org/en/release-3.4.x/how_to/custom_plugins.html>` to learn more.

Once you have created your CMS plugin, you will need to manually add it to the "Registration Summary"
page.  To do so, follow these steps:

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
   this placeholder to add a plugin, and from the available plugins choose
   your payment processor's plugin.
