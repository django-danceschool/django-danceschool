from django.utils.translation import ugettext_lazy as _

# This is the list of possible bases.  Revenues are booked by receipt
# and are not approved, so paymentDate and approvalDate are actually
# receivedDate for revenues.
EXPENSE_BASES = {
    'accrualDate': _('Date of Accrual (e.g. Series end date)'),
    'submissionDate': _('Date of Submission'),
    'paymentDate': _('Date of Payment/Receipt'),
    'approvalDate': _('Date of Approval/Receipt'),
}
