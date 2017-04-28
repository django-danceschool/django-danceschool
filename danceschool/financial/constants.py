from django.utils.translation import ugettext_lazy as _

# These are explicitly defined for easy reference
CASH_PAYMENTMETHOD_ID = 1
PAYPAL_PAYMENTMETHOD_ID = 2
VENMO_PAYMENTMETHOD_ID = 3
BANK_PAYMENTMETHOD_ID = 4
CHECK_PAYMENTMETHOD_ID = 5

# These are the payment method choices that are listed in the admin and
# therefore available for reporting purposes.
REVENUE_PAYMENTMETHOD_CHOICES = (
    (None,'-----'),
    (CASH_PAYMENTMETHOD_ID,_('Cash')),
    (PAYPAL_PAYMENTMETHOD_ID,_('Paypal')),
    (VENMO_PAYMENTMETHOD_ID,_('Venmo')),
    (BANK_PAYMENTMETHOD_ID,_('Bank/Debit Card')),
    (CHECK_PAYMENTMETHOD_ID,_('Check')),
)

# These are the payment methods that support automated refund processing.
REVENUE_AUTOREFUND_PAYMENTMETHODS = (
    PAYPAL_PAYMENTMETHOD_ID,
)

# These are the payment method choices that are listed in the admin and
# therefore available for reporting purposes.
EXPENSE_PAYMENTMETHOD_CHOICES = (
    (None,'-----'),
    (CASH_PAYMENTMETHOD_ID,_('Cash')),
    (PAYPAL_PAYMENTMETHOD_ID,_('Paypal')),
    (VENMO_PAYMENTMETHOD_ID,_('Venmo')),
    (BANK_PAYMENTMETHOD_ID,_('Bank/Debit Card')),
    (CHECK_PAYMENTMETHOD_ID,_('Check')),
)

# This is the list of possible bases.  Revenues are booked by receipt
# and are not approved, so paymentDate and approvalDate are actually
# receivedDate for revenues.
EXPENSE_BASES = {
    'accrualDate': _('Date of Accrual (e.g. Series end date)'),
    'submissionDate': _('Date of Submission'),
    'paymentDate': _('Date of Payment/Receipt'),
    'approvalDate': _('Date of Approval/Receipt'),
}
