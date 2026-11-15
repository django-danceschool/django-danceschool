Financial Functions
===================

The ``danceschool.financial`` app, if installed, provides the ability to do detailed financial accounting of a school's revenues and expenses.  Because this system hooks into the core app, it can automatically keep track of revenues received from students registering for classes.  Additionally, it can be set to automatically generate expense items for instructors, substitute teachers, venue rental, and other expenses that are either paid by the hour or on a daily/weekly/monthly basis.

This page describes how to submit individual expense and revenue items, how to set up autogeneration of expense and revenue items, and how to generate reports of financial activity.

Reporting Individual Expense and Revenue Items
----------------------------------------------

For miscellaneous expenses and other overhead, the app includes an expense reporting form that permits easy entry of expenses, including optional file attachment for receipts.  To use this form, go to the CMS toolbar and choose *Finances > Submit Expenses.*   This form will allow users to submit both flat-price expenses as well as hours of work (for things such as administrative labor).  The total expense for hours submitted is calculated using the default rate for the Expense category chosen.  

When submitting expenses for reimbursement as opposed to compensation, be sure to check the "Reimbursement" box.  This ensures that individuals' taxable compensation is recorded accurately.

Users with sufficient permissions may also have the option to mark expenses as approved and paid at the time of submission.  If you record payments in this way, it is strongly recommended that you enter the payment date in which the expense was actually paid.  This ensures that your periodic accounting statements remain accurate.

Miscellaneous revenues are less common, but may be used for things like practice sessions where students pay in cash and the standard registration system is not needed.  To use this form, choose *Finances > Submit Revenues* from the CMS toolbar.  Revenues can be associated with a specific class series or event, and receipts can be attached.  If you allow instructors or other staff members to collect cash payments temporarily, then you can use the "Cash currenly in possession of" field to indicate the individual that collected the revenue, so that you can be sure that the money is eventually given to the person responsible for its deposit.

Automatic Generation of Expense and Revenue Items
-------------------------------------------------

Enabling Generation
^^^^^^^^^^^^^^^^^^^

If you ran the ``setupschool`` script when installing your project, then you have already selected whether or not to automatically enable automatic generation of expense and revenue items for the above items.  However, if you did not take this step, then you can enable automatic generation by going to the site preferences from the CMS toolbar at Apps > Global Settings.  From there, select the Financial section, and you will see checkboxes for enabling/disabling automatic generation of expenses.  You will also see options to set the categories into which these automatically generated expenses are filed (usually the defaults will be fine), and an option to restrict how far back in time the auto-generation process for Registration proceeds (which you are unlikely to need to change).

There are no further steps to setting up automatic generation of Revenue Items for registrations.  However, for venue rental expenses, staff expenses, or other repeated expenses, you will need to set up the rules with which expenses are generated (see below).

**Note:** By default, automatic generation of expense and revenue items happens once per hour.  Through the Repeated Expense Rule admin interface, it is also possible to generate expenses immediately by selecting the rules you wish to apply and choosing "Generate expenses for selected repeated expense rules" from the dropdown.  If you are not seeing automatic generation of expenses occurring hourly, be sure that Huey is running.  See :ref:`huey_setup` for more details.

Setting Repeated Expense Rules
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There are two ways to set up repeated expense generation rules for Locations and Staff Members:

1.  Through the administrative change view for the specific Location or Staff Member whose rules you wish to set/change.  Expand the collapsible section entitled "Locations' rental information" or "Staff members' wage/salary information" to edit details from here.
2.  Through the Repeated Expense Rule admin, accessible from the CMS toolbar at *Finances > Related Items > Repeated Expense Rules.*

Rules can be set to generate expenses hourly, daily, weekly, or monthly.  The "Day starts at," "week starts at," and "month starts at," parameters define the time point at which expense windows begin and end ("week starts at" and "month starts at" are ignored for expenses that are not weekly or monthly, respectively).  And, if you use the admin interface option #2, you also have the ability to specify explicit start/end dates beyond which expenses will not be generated.

For "generic" repeated expenses that are not associated with a Location or a Staff Member, you will need to use the admin interface as specifed in option 2.  Here, you will be presented with the option to give this rule a name for record-keeping (e.g. "web hosting fees"), along with options to specify the category of the expense and the recipient of the expense payment.  Finally, you have the option to automatically designate these expenses as approved and/or paid.

For expense items associated with Locations or Staff Members, the script generates expenses only in response to the existence of events.  So, for example, an hourly expense for an Instructor's instructional time is generated only for the hours in which the individual is scheduled to teach.  Daily, weekly, and monthly expenses are generated only if the location or staff member was scheduled in that period.  In contrast, "generic" repeated expenses are generated regardless of whether any events were scheduled in the period in question.  So, be sure to apply "hourly" and "daily" generic expense rules with caution.

If you have automatically generated expenses erroneously, you may simply go to the Expense Item admin interface from the CMS toolbar at *Finances > Related Items > Expense Items,* filter by the rule that was used to generate the expenses, and delete the offending expense items.  It is also acceptable to modify or delete expense items that are exceptions to the regular rule from this point.  However, be advised that if you delete or change the time window of an expense item and do not update the generation rule that was used to create it, then you may end up with repeated expense items at the next occasion when that rule is applied.


Categories for Staff Members
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you are editing the wage/salary information for an instructor or other staff member, you will see a "Category" field, populated with the different categories of event staffing that you have defined on your site (Class Instruction and Substitute Teaching are automatically specified as categories).  This field is optional, but recommended.  When the script runs that generates expense items, it looks first for a rule to apply that is specific to the category of staffing that is scheduled.  If no such rule is found, it then looks for a "catch all" rule in which no category of staffing is specified.  If no such rule is found, then the script does not automatically generate expenses for that staffer.

Note that there can be only one rule per instructor and category, so that there is always a unique rule that is applied for any given staffing of an event.


Financial Summaries
-------------------

Because the financial app allows for comprehensive expense and revenue tracking, it is possible to produce simple financial summaries that allow you to get a snapshot of your school's financial performance.

- **Monthly summary:** Go to "View Monthly Financial Summary" in the "Finances" menu of the CMS toolbar.
- **Event summary:** Go to "View Financial Summary By Event."  Note that these event-specific entries do not include any revenues or expenses that are not associated with a specific event, such as administrative expenses
- **Detailed categorical breakdowns:** Go to "Detailed Breakdown" and select the period desired, or select a specific month from the monthly summary page.  From the detailed categorical breakdown, you can can also quickly find links to specific expense and revenue items in order to make corrections.
  
Note also that for accounting purposes, monthly and detailed summaries can be constructed on several different bases, which can be selected within each page:

- **Payment basis:** Summaries are constructed based on when money is received or spent.  This is what is typically used for "cash accounting" for tax purposes.
- **Accrual basis:** Summaries are constructed based on a notion of when the money is "owed" (e.g. at the end of a class series for instructors).  This can help to get a more accurate picture of your financial performance   Please be advised that the accrual basis constructed in this project almost certainly does not correspond to generally accepted accounting practices, and therefore it is not recommended to use these statements as a basis for so-called "accrual accounting" for tax purposes.
- **Submission basis:** Summaries are constructed based on when revenue and expense items are submitted to the database.

Sales Tax and Tax Jurisdictions
-------------------------------

Sales tax (or a similar tax, such as an admissions tax) is charged according to *tax jurisdictions*.  A tax jurisdiction is an authority to which you owe tax; depending on local rules this may be a state, a county, or a city.  If no tax jurisdiction applies to a sale, then no tax is charged.

To set up sales tax:

1. Go to "Finances > Related Items > Tax Jurisdictions" in the CMS toolbar and create a jurisdiction with its **default tax rate**.  If some things are taxed differently in that jurisdiction, add rules beneath it.  A rule can apply to a type of item (class series, public events, private lessons, or merchandise) or to a specific category of class series or public events.  Enter a rate of 0 for anything that is exempt.
2. Assign each **Location** to its tax jurisdiction.  Registrations are taxed based on where the event takes place, regardless of where or when the customer pays.
3. Assign each **at-the-door register** to its tax jurisdiction.  Merchandise is taxed based on the register through which it is sold, so each register should be used in only one jurisdiction.
4. Optionally, choose a **default tax jurisdiction** under "Registration" in the site preferences.  This is used for anything that has no jurisdiction of its own, such as an event with no location.

The rate for an individual event or merchandise item can be overridden using its "Sales tax rate override" field.  Leave that field blank to follow the rules of the jurisdiction, or enter 0 to make the item exempt.

**Only one tax jurisdiction and one tax rate apply to each item that is sold.**  If more than one authority taxes sales at the same place (for example, a state sales tax and a county sales tax), do not create a jurisdiction for each of them.  Instead, create a single jurisdiction for that place whose rates are the combined total of all the taxes that apply there (for example, "Springfield (state and county)" at 7.5% for a 6% state tax and a 1.5% county tax).  The same is true of the "Sales tax rate override" field: it replaces the rate only, so enter the combined rate, and the tax is still reported under the jurisdiction of the location or register.  The system reports one tax amount for each jurisdiction, so if the taxes are filed separately, you will need to divide that amount between the authorities yourself in proportion to their rates.

Each invoice item records the tax rate and jurisdiction that applied when it was sold, and a single invoice may include items from more than one jurisdiction.  To see how much tax is owed to each authority, go to "Finances > Financial Summaries > Sales Tax By Jurisdiction".  The report can be based on when payment was received or on the accrual date, and it can be exported as a CSV file.

The site preference "Buyer pays sales tax" continues to determine whether tax is added on top of your prices or is treated as included in them.

Applying Tax Rules to Existing Invoices
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Invoices that were created before your tax jurisdictions were set up do not record a jurisdiction, and they may not have had the correct tax applied.  The ``backfill_tax_jurisdictions`` management command applies your current rules to existing invoices.  By default it only reports what it would do, broken down by jurisdiction and month, and it changes nothing until you add ``--commit``:

::

    python manage.py backfill_tax_jurisdictions --mode=carve-out --start=2025-01-01 --end=2025-12-31

There are three modes:

- ``--mode=label`` (the default) records the tax jurisdiction on each invoice item and changes no amounts.
- ``--mode=carve-out`` also corrects items whose tax is too low, by treating the amount that was collected as having included the tax.  The price of the item is revised downward by the amount of the tax, so the amount collected does not change and paid invoices remain paid.  The original amounts are kept in the item's additional data.
- ``--mode=add`` also corrects items whose tax is too low, by adding the tax on top of the price.  Because this leaves a balance due, it is only permitted for invoices that are still unpaid.  If paid invoices are affected, the command lists them and stops; re-open those invoices yourself, or pass ``--skip-paid`` to proceed with the others.

Use ``--start``, ``--end`` and ``--jurisdiction`` to limit which invoices are considered.  The command applies the rules as they are now, so if your rates have changed over time, run it separately for each period with the rules set as they were.  Items that have been refunded, and items with more tax recorded than is now due, are never changed automatically; they are counted in the report so that you can review them.

Exporting Financial Data
------------------------

If you need to export financial data for analysis using another method (e.g. Excel), you can do so from the Monthly Financial Summary view by clicking the buttons under the "Export Financial Data (CSV)" heading.
