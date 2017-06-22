Financial Functions
===================

The ``danceschool.financial`` app, if installed, provides the ability to do detailed financial accounting of a school's revenues and expenses.  Because this system hooks into the core app, it can automatically keep track of revenues received from students registering for classes.  Additionally, it can be set to automatically generate expense items for instructors, substitute teacher, and venue rental.  If you ran the ``setupschool`` script when installing your project, then you have already selected whether or not to automatically generate expense and revenue items for the above items.

This page describes how to submit additional expenses and revenues, as well as how to generate reports of financial activity.

Expense and Revenue Reporting
-----------------------------

For miscellaneous expenses and other overhead, the app includes an expense reporting form that permits easy entry of expenses, including optional file attachment for receipts.  To use this form, choose "Submit Expenses" under the "Finances" menu of the CMS toolbar.  This form will allow users to submit both flat-price expenses as well as hours of work (for things such as administrative labor).  The total expense for hours submitted is calculated using the default rate for the Expense category chosen.  

When submitting expenses for reimbursement as opposed to compensation, be sure to check the "Reimbursement" box.  This ensures that individuals' taxable compensation is recorded accurately.

Miscellaneous revenues are less common, but may be used for things like practice sessions where students pay in cash and the standard registration system is not needed.  To use this form, choose "Submit Revenues" under the "Finances" menu of the CMS toolbar.  Revenues can be associated with a specific class series or event, and receipts can be attached.

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

Exporting Financial Data
------------------------

If you need to export financial data for analysis using another method (e.g. Excel), you can do so from the Monthly Financial Summary view by clicking the buttons under the "Export Financial Data (CSV)" heading.
