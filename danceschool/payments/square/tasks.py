from huey.contrib.djhuey import db_task


@db_task(retries=3)
def updateSquareFees(paymentRecord):
    '''
    The Square Checkout API does not calculate fees immediately, so this task is
    called to be asynchronously run 1 minute after the initial transaction, so that
    any Invoice or ExpenseItem associated with this transaction also remains accurate.
    '''

    fees = paymentRecord.netFees
    invoice = paymentRecord.invoice
    invoice.fees = fees
    invoice.save()
    invoice.allocateFees()
    return fees
