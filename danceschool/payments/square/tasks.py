from huey.contrib.djhuey import db_task

from .helpers import getNetFees


@db_task(retries=3)
def updateSquareFees(paymentRecord):
    '''
    The Square Checkout API does not calculate fees immediately, so this task is
    called to be asynchronously run 1 minute after the initial transaction, so that
    any Invoice or ExpenseItem associated with this transaction also remains accurate.
    '''

    # Get payments and refunds and simultaneously update the cache for each.
    payments=paymentRecord.getPayments(use_cache=False, commit=False)
    refunds=paymentRecord.getRefunds(
        payments=payments, use_cache=False, commit=False
    )

    fees = getNetFees(
        order_id=paymentRecord.orderId, client=paymentRecord.client,
        payments=payments, refunds=refunds
    )

    invoice = paymentRecord.invoice
    invoice.updateTotals(save=True, allocateAmounts={'fees': fees})
    return fees
