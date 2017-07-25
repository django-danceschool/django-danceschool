Discounts, Vouchers, Gift Certificates
======================================

Overview of Pricing
-------------------

Most classes use a common pricing structure.  Therefore, instead of custom per-series pricing, each class or event that has registration requires a Pricing Tier, which defines the base prices for both online registration and at-the-door registration.  There is no limit on the number of tiers, so if you need custom pricing for a specific event for some reason, just create a new pricing tier.

When creating a new class/series, you will be able to select from existing pricing tiers, or create a new one by clicking the "Add" button (plug sign) next to the pricing tier field.  Additionally, if you ran ``manage.py setupschool`` to set up your initial installation, then it is likely that you have already created an initial pricing tier.

Discounts
---------

If you have installed the ``danceschool.discounts`` app, then you are able to offer sophisticated discounts based on the content of a customer's registration.  Here are some examples of things that the discount app can handle:

- x% discount for all first-time customers
- $y discount for registering for two or more regular classes at once
- An 'all-in pass' price where the user can register for as many classes as they would like for a flat fee

Discounts are applied automatically, and the lowest-price available discount is automatically applied.  However, only one discount at a time can be applied to a registration.

Creating A Simple Discount
^^^^^^^^^^^^^^^^^^^^^^^^^^

All discounts are determined using a straightforward points-based system.  Each pricing tier can assigned both a "point group" (a type of points, defined by you) and a number of points.  A customer's registration is determined to be eligible for a specific discount if the contents meet or exceed the required number of points needed for that discount to apply.

For example, suppose that in your school, you would like to offer a simple discount of $10 off to students who register for two or more of your regular weekly class series at the same time.  To implement this discount, just follow these steps:

1.	In the CMS toolbar, go to **Events > Related Items > Pricing Tier** and select the pricing tier that applies to your regular weekly class series to edit it.
2.	Under "Pricing tier discount groups," select "Add another pricing tier discount group" to define the point group and the number of points that each regular weekly class receives.  For a simple discount such as this, we can simply add a new point group, such as "Individual weekly class series points," and make each item under the regular pricing tier worth one point.
3.	Return to the CMS toolbar (you may need to go back to a non-administrative page to access it) and go to **Finances > Related Items > Discounts** to access the list of existing discounts, and on the listing page, select he "Add Discount" button to create a new discount.
4.  Fill out the information for the new discount.  Give the discount a name, ensure that the "Active" box is checked, and under "Discount Type," select "Dollar Discount from Regular Price."  Then, under "Amount of Dollar Discount," enter 10 for a $10 flat discount.  Under "Required components of discount," select the point group that you created (i.e. "Individual weekly class series points") and enter 2 for quantity.
5.  Click save and you're done!  Now, all students who sign up for two or more regular weekly class series at the same time will automatically receive $10 off the regular price.

More Advanced Discounts (Examples)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Discounts Based on Hours of Class
"""""""""""""""""""""""""""""""""

Because of the point-based nature of the discount system, it is easy to create more sophisticated discounts.  For example, suppose that you want to provide a sliding discount based on the number of hours of class that a student signs up for.  If you have different pricing tiers corresponding to classes of different lengths (e.g. two weeks of class, four weeks of class, etc.), just give each pricing tier a number of points corresponding to the number of hours (e.g. 2 and 4 points, respectively).  Then, define discounts that automatically apply based on the number of those points.

All-in Passes
"""""""""""""

"All-in passes" are also easy to create using the discount system.  When entering the required components for an "Exact Specified Price" discount, simply check the "Applies to all within Point Group" box to ensure that the flat price is applied to the given quantity *or more* or points within the specified point group.

Vouchers
--------

If you have installed the ``danceschool.vouchers`` app, then you are able to offer voucher codes, gift certificates, and referral/referree discounts.

Vouchers can be public (e.g. publicly advertised discount codes), or they can be forcibly private (only usable by a specific customer).  They can be restricted to apply only to first-time students, or to apply only to prior students.  It is also possible to add credits to previously generated voucher codes, which can be useful if you are, for example, providing vouchers to students who volunteer for the school.

Creating Vouchers
^^^^^^^^^^^^^^^^^

To create a new Voucher, just use the CMS toolbar to go to ** Finances > Related Items > Vouchers ** and click the "Add Voucher" button on the listing page.  There, you will need to add the following pieces of information

-	The voucher code (must be unique)
-	A name (to be displayed when the customer enters the voucher code)
-	A category (Some basic categories are defined, or you can also create new categories for different types of vouchers you may want to offer).
-	An "original amount" for the voucher.
 	
You can also optionally add the following pieces of information/restrictions:

-	A description (for internal use only)
-	A maximum amount per use.  For public vouchers that are meant as discount codes, be sure to enter this field, and to enter an "Original Amount" that is large enough to apply numerous times.  E.g. for a $10 discount for the first 100 customers, enter $1,000 as the original amount, and a $10 max amount per use.
-	An expiration date.  If no expiration is specified, then the voucher never expires.
-	Restrictions that limit a voucher to a single use, and restrictions that limit a voucher to use by first-time customers (customers not in the database) or existing customers (in the database) only.
-	Restrictions that allow a voucher to be used only for specific dance types/levels, for specific class series (specified by the Class Description), or for specific customers.
-	Additional voucher credits, for "topping up" a voucher.

Note on Voucher Restrictions
""""""""""""""""""""""""""""

If specified, voucher restrictions (e.g. based on dance level) require that *all* items within a user's registration meet *one of* the restrictions specified.  So, for example, if I want a customer to be able to use a voucher for either our "Lindy 1" or "Lindy 2" classes, I would specify *both* Lindy 1 and Lindy 2 as the dance level voucher restriction.  Then, if that customer registers for *either* Lindy 1 or Lindy 2, and they enter the voucher code, they will receive the discount.  However, if their registration also includes items that are not Lindy 1 or Lindy 2, then they will be considered to be ineligible for the voucher code.


Gift Certificates
-----------------

A gift certificate is simply a voucher code.  However, if it is enabled by your payment processor (as it is for the built-in Paypal and Stripe integrations), then it is possible to accept online payments for gift certificates.  In this case, a voucher code is generated automatically for the amount paid, and the submitting user is sent an email with a PDF attachment that they can choose to print and give as a gift.  The system does all of the work for you, so you don't need to do anything but add the option 

To add gift certificate functionality, go to the page where you want to allow users to purchase gift certificates, Edit the page in structure mode, and in the block of the page where you want the purchase button to be located (e.g. "Content"), add either a "Payapl Gift Certificate Form" plugin or a "Stripe Gift Certificate Form" plugin.  You will be asked to enter both the default amount of the gift certificate (which can be changed by the customer), and the page to which the customer will be redirected after they have purchased their gift certificate.  Save the page, and you're all set!

Both the default text of the gift certificate email as well as the default text of the PDF attachment are loaded as email templates when the school is set up.  To modify their contents, just use the CMS toolbar to navigate to ** Content > Manage Email Templates ** and select either the "Gift Certificate Purchase Confirmation Email" or the "Gift Certificate Purchase PDF Text" templates to edit them.  You may also wish to override the template ``vouchers/pdf/giftcertificate_template.html`` in your custom app to generate a PDF gift certificate with a different layout, or to add your own logo, etc.

Referral/Referree Program
-------------------------

Some schools like to offer referral discounts to encourage their students to advertise on their behalf.  This project provides a simple way of running a referral/referee discount system.  If enabled, then each of your customers will automatically be given the ability to refer other customers using a special voucher code.  Customers who use this voucher code will receive a "referree" discount when they sign up for their first class, while the customer whose voucher code is used will receive a "referrer" discount.

To enable to the referral program and set the amounts for referree and referrer discounts, use the CMS toolbar to navigate to **Apps > Global Settings**.  From there, select the "Referrals" preference page, where you will find a checkbox to enable/disable the referral program, and the ability to modify the discount amounts. 

Accessing a Customer's Referral Code
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In order to access the referral system, your customers must create a user account.  Once they have done so, they can login to access the "My Account" page (It is the page that is automatically shown when a user logs in).  On this page, they should see a code under "Customer Referral ID."  This is the voucher code that they need to use in order to refer customers.  When another new customer enters this voucher code, that (new) customer will automatically receive the referree discount, and the customer whose code is used will receive a referral discount that will be automatically applied against their next registration.

Examples of Usage
^^^^^^^^^^^^^^^^^

-	Send an email to customers including their referral code and encouraging them to sign up their friends using it
-	Give customers flyers with their referral code written on them and encourage them to post flyers to get discounts
