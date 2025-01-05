from django.conf import settings
from django.utils import timezone
from huey.contrib.djhuey import db_task, db_periodic_task
from huey import crontab
import logging

from danceschool.core.utils.timezone import ensure_localtime
from .api_client import api_client as client


# Define logger for this file
logger = logging.getLogger(__name__)


@db_task(retries=3)
def updateSquareFees(paymentRecord):
    '''
    The Square Checkout API does not calculate fees immediately, so this task is
    called to be asynchronously run 1 minute after the initial transaction, so that
    any Invoice or ExpenseItem associated with this transaction also remains accurate.
    '''

    # Get payments and refunds and simultaneously update the cache for each.
    # This ensures that fees are calculated properly.
    payment=paymentRecord.getPayment(use_cache=False, commit=False)
    refunds=paymentRecord.getRefunds(
        payment=payment, use_cache=False, commit=True
    )

    invoice = paymentRecord.invoice
    invoice.updateTotals(save=True, allocateAmounts={'fees': paymentRecord.netFees})
    return fees


@db_periodic_task(crontab(hour='*'))
def updateSquarePaymentRecords(update_all=False, begin_time=None):
    '''
    To keep the Square records on the server in sync with those reported by
    Square, this task pulls down any recent updates to the Square payment
    records using the Square API, and it either attaches this information to the
    JSON data of any existing SquarePaymentRecord, or it creates a new record in
    the database.
    '''

    from .models import SquarePaymentRecord

    def pop_by_key_value(list_of_dicts, key, value):
        '''
        Pops the first dictionary from a list of dictionaries that matches the given key-value pair.
        '''
        for i, d in enumerate(list_of_dicts):
            if d.get(key) == value:
                return list_of_dicts.pop(i)
        return None

    logger.info('Syncing local Square payment records to API responses.')

    api_kwargs = {}
    refund_api_kwargs = {}

    # Use the database to determine how recent the most recent updates are.
    if not update_all and not begin_time:
        last_updated = SquarePaymentRecord.objects.filter(
            data__apiPaymentResponseDate__isnull=False
        ).order_by(
            '-data__apiPaymentResponseDate'
        ).values_list('data__apiPaymentResponseDate', flat=True).first()

        if last_updated:
            api_kwargs['updated_at_begin_time'] = last_updated
            refund_api_kwargs['begin_time'] = last_updated
    elif begin_time:
            api_kwargs['updated_at_begin_time'] = begin_time.isoformat()
            refund_api_kwargs['begin_time'] = begin_time.isoformat()

    # Set the time of this update to associate with all records just before we
    # call the API.
    update_time = ensure_localtime(timezone.now()).isoformat()

    # Get the set of payments that have been updated, which may be on multiple
    # pages.
    cursor = None
    has_next_page = True
    remaining_payments = []

    while has_next_page:
        payments_page = client.payments.list_payments(
            location_id=settings.SQUARE_LOCATION_ID,
            cursor=cursor,
            **api_kwargs
        )
        if not payments_page.errors:
            cursor = payments_page.cursor
            remaining_payments += payments_page.body.get('payments', [])
        if payments_page.errors or cursor is None:
            has_next_page = False

    # Now, apply a similar procedure to collect refund information so that we
    # can update associated payment records.
    cursor = None
    has_next_page = True
    all_refunds = []

    while has_next_page:
        refunds_page = client.refunds.list_payment_refunds(
            location_id=settings.SQUARE_LOCATION_ID,
            cursor=cursor,
            **refund_api_kwargs
        )
        if not refunds_page.errors:
            cursor = refunds_page.cursor
            all_refunds += refunds_page.body.get('refunds', [])
        if refunds_page.errors or cursor is None:
            has_next_page = False

    # Get the local records associated with these updated API records. Their
    # JSON data will be updated to reflect the API responses.
    existing_records = SquarePaymentRecords.objects.filter(
        paymentId__in=(
            [x.get('id') for x in remaining_payments] +
            [x.get('payment_id') for x in all_refunds]
        )
    )

    for record in existing_records:
        # First, get the payment API data associated with this record, and
        # simply replace the JSON data if a new API response exists. Notice also
        # that the data are popped from the full list, so that what will
        # remain after this loop are the set of API payments that still lack a
        # SquarePaymentRecord.
        payment_response = pop_by_key_value(remaining_payments, 'id', record.PaymentId)
        if payment_response:
            record.data.update({
                'apiPaymentResponse': payment_response,
                'apiPaymentResponseDate': update_time,
            })

        # There can be multiple refunds associated with a payment record, so
        # first, get the set of refunds associated with this one.
        this_record_refunds = [
            x for x in all_refunds if x.get('payment_id') == record.paymentId
        ]
        if this_record_refunds:
            # Pop off any old records in the JSON data that are associated with the
            # new/updated refunds, and then append the new records received from the
            # API.
            refund_data = record.data.get('apiRefundResponse', [])
            popped = [
                pop_by_key_value(refund_data, 'id', x.get('id'))
                for x in this_record_refunds
            ]
            refund_data += this_record_refunds
            record.data.update({
                'apiRefundResponse': refund_data,
                'apiRefundResponseDate': update_time,
            })

    # Save the updated data for existing records.
    SquarePaymentRecord.objects.bulk_update(
        existing_records, ['data',], batch_size=1000
    )
    logger.info(f'Updated {len(existing_records)} existing SquarePaymentRecords.')


    # The remaining records in remaining_payments are Square payments for which
    # there does not yet exist a SquarePaymentRecord in the database. So, these
    # records are created, but they are not yet associated with an invoice or
    # a revenue item, meaning that financial reports will not yet be in sync
    # with actual payments received. Nonetheless, adding them to the database
    # here allows a user to generate an invoice later, or to associate these
    # payments with an existing invoice, an event, etc.
    SquarePaymentRecord.objects.bulk_create([
        SquarePaymentRecord(
            paymentId=x.get('id'),
            orderId=x.get('order_id'),
            locationId=x.get('location_id'),
            data={
                'apiPaymentResponse': x,
                'apiPaymentResponseDate': update_time
            }
        )
        for x in remaining_payments
    ])

    logger.info(f'Created {len(remaining_payments)} new SquarePaymentRecords.')
