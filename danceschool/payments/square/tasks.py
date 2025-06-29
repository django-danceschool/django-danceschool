from django.conf import settings
from django.utils import timezone
from huey.contrib.djhuey import db_task, db_periodic_task
from huey import crontab
import logging
from datetime import timedelta
from square.core.api_error import ApiError

from .api_client import iso_timestamp_to_localtime
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
    return paymentRecord.netFees


@db_periodic_task(crontab(minute='*/60'))
def updateSquarePaymentRecords(update_all=False, begin_time=None):
    '''
    To keep the Square records on the server in sync with those reported by
    Square, this task pulls down any recent updates to the Square payment
    records using the Square API, and it either attaches this information to the
    JSON data of any existing SquarePaymentRecord, or it creates a new record in
    the database.
    '''

    from .models import SquarePaymentRecord

    logger.info('Syncing local Square payment records to API responses.')

    api_kwargs = {}
    refund_api_kwargs = {}

    # Use the database to determine how recent the most recent updates are.
    if not update_all and not begin_time:
        last_updated = iso_timestamp_to_localtime(
            SquarePaymentRecord.objects.filter(
                data__apiPaymentResponseDate__isnull=False
            ).order_by(
                '-data__apiPaymentResponseDate'
            ).values_list('data__apiPaymentResponseDate', flat=True).first()
        )

        if last_updated:
            api_kwargs['updated_at_begin_time'] = last_updated - timedelta(hours=6)
            refund_api_kwargs['begin_time'] = last_updated - timedelta(hours=6)
    elif begin_time:
        api_kwargs['updated_at_begin_time'] = begin_time.isoformat()
        refund_api_kwargs['begin_time'] = begin_time.isoformat()

    # Set the time of this update to associate with all records just before we
    # call the API.
    update_time = timezone.localtime().isoformat()

    # Get the set of payments that have been updated. The updated Square APIs
    # handle pagination under the hood.
    remaining_payments = []
    remaining_payment_ids = []

    try:
        payments_response = client.payments.list(
            location_id=settings.SQUARE_LOCATION_ID,
            **api_kwargs
        )
        for payment in payments_response:
            # We only want completed payments to be included in our database,
            # but the API cannot filter, so we filter the response list here
            # before further processing.
            if payment.status == 'COMPLETED':
                remaining_payments.append(payment)
                remaining_payment_ids.append(payment.id)
    except ApiError as e:
        pass

    # Now, apply a similar procedure to collect refund information so that we
    # can update associated payment records.
    all_refunds = []
    all_refund_ids = []

    try:
        refunds_response = client.refunds.list(
            location_id=settings.SQUARE_LOCATION_ID,
            **refund_api_kwargs
        )
        for refund in refunds_response:
            all_refunds.append(refund)
            all_refund_ids.append(refund.payment_id)  
    except ApiError as e:
        pass

    # Get the local records associated with these updated API records. Their
    # JSON data will be updated to reflect the API responses.
    existing_records = list(SquarePaymentRecord.objects.filter(
        paymentId__in=(remaining_payment_ids + all_refund_ids)
    ))

    for record in existing_records.copy():
        # First, get the payment API data associated with this record, and
        # simply replace the JSON data if a new API response exists. Notice also
        # that the data are popped from the full list, so that what will
        # remain after this loop are the set of API payments that still lack a
        # SquarePaymentRecord. Finally, we are iterating over a shallow copy so
        # that we can remove items that don't need to be updated at all.
        payment_response = next((x for x in remaining_payments if x.id == record.paymentId), None)
        if payment_response:
            if (
                payment_response.version_token !=
                record.data.get('apiPaymentResponse', {}).get('version_token')
            ):
                record.data.update({
                    'apiPaymentResponse': payment_response.dict(),
                    'apiPaymentResponseDate': update_time,
                })

        # There can be multiple refunds associated with a payment record, so
        # first, get the set of refunds associated with this one.
        this_record_api_refunds = [
            x for x in all_refunds if x.payment_id == record.paymentId
        ]
        if this_record_api_refunds:
            # Pop off any old records in the JSON data that are associated with the
            # new/updated refunds, and then append the new records received from the
            # API if the update stamp has changed.
            old_db_refund_data = record.data.get('apiRefundResponse', [])
            this_record_refund_ids = [x.id for x in this_record_api_refunds]

            # We will only update records that have a reason to be updated.
            flag_to_update = False

            # This will be filled in with records that were found in both the
            # API response and the database for additional checking.
            existing_db_refund_data = []
            
            # This will be iteratively filled in with replacement records below,
            # but will only be saved to DB if the flag is set because something
            # has changed.
            updated_refund_data = []

            for old in old_db_refund_data:
                if old.get('id') in this_record_refund_ids:
                    existing_db_refund_data.append(old)
                else:
                    # If a refund occurred before the API time window, then it still
                    # belongs on the DB record, but is presumed not to have changed.
                    updated_refund_data.append(old)
            
            # Now loop through all the API records and compare them to any
            # existing records in the database. If something has changed, then
            # we will update the database record.
            for new in this_record_api_refunds:
                existing = next((x for x in existing_db_refund_data if x.get('id') == new.id), {})
                if existing and (new.updated_at != existing.get('updated_at')):
                    flag_to_update  = True
                updated_refund_data.append(new.dict())

            # The updated_refund_data is now complete, but the flag identifies
            # whether a database update is needed.
            if flag_to_update:
                record.data.update({
                    'apiRefundResponse': updated_refund_data,
                    'apiRefundResponseDate': update_time,
                })
            
        if not (
            (record.data.get('apiPaymentResponseDate') == update_time) or
            (record.data.get('apiRefundResponseDate') == update_time)
        ):
            # Nothing in this record was updated, so don't include it in the
            # bulk update procedure.
            existing_records.remove(record)

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
    # payments with an existing invoice, an event, etc. Note that the
    # bulk_create method is not available here because this model is
    # polymorphic, so we loop through records and create one at a time.
    created_objects = []

    for x in remaining_payments:
        created_objects.append(
            SquarePaymentRecord.objects.create(
                paymentId=x.id,
                orderId=x.order_id,
                locationId=x.location_id,
                data={
                    'apiPaymentResponse': x.dict(),
                    'apiPaymentResponseDate': update_time
                }
            )
        )

    logger.info(f'Created {len(created_objects)} new SquarePaymentRecords.')


@db_periodic_task(crontab(minute='*/60'))
def updateSquarePayoutRecords(update_all=False, begin_time=None):
    '''
    To keep the Square records on the server in sync with those reported by
    Square, this task pulls down any recent updates to the Square payment
    records using the Square API, and it either attaches this information to the
    JSON data of any existing SquarePaymentRecord, or it creates a new record in
    the database.
    '''

    from .models import SquarePayoutRecord

    logger.info('Syncing local Square payout records to API responses.')

    api_kwargs = {}

    # Use the database to determine how recent the most recent updates are.
    if not update_all and not begin_time:
        last_updated = iso_timestamp_to_localtime(
            SquarePayoutRecord.objects.filter(
                data__apiPayoutResponseDate__isnull=False
            ).order_by(
                '-data__apiPayoutResponseDate'
            ).values_list('data__apiPayoutResponseDate', flat=True).first()
        )

        if last_updated:
            api_kwargs['begin_time'] = last_updated - timedelta(hours=6)
    elif begin_time:
        api_kwargs['begin_time'] = begin_time.isoformat()

    # Set the time of this update to associate with all records just before we
    # call the API.
    update_time = timezone.localtime().isoformat()

    # Get the set of payments that have been updated.
    remaining_payouts = []

    try:
        payouts_response = client.payouts.list(
            location_id=settings.SQUARE_LOCATION_ID,
            **api_kwargs
        )
        for payout in payouts_response:
            # We only want submitted payouts to be included in our database, but
            # the API cannot filter, so we filter the response list here before
            # further processing.
            if payout.status != 'FAILED':
                remaining_payouts.append(payout)
    except ApiError as e:
        pass

    # Get the local records associated with these updated API records. Their
    # JSON data will be updated to reflect the API responses.
    existing_records = list(SquarePayoutRecord.objects.filter(
        payoutId__in=[x.id for x in remaining_payouts]
    ))

    for record in existing_records.copy():
        # First, get the payout API data associated with this record, and
        # simply replace the JSON data if a new API response exists. Notice also
        # that the data are popped from the full list, so that what will
        # remain after this loop are the set of API payouts that still lack a
        # SquarePayoutRecord. Finally, we are iterating over a shallow copy so that we
        # can remove items that don't need to be updated at all.
        payout_response = next((x for x in remaining_payouts if x.id == record.payoutId), None)
        if payout_response:
            if (
                payout_response.version !=
                record.data.get('apiPayoutResponse', {}).get('version')
            ):
                record.data.update({
                    'apiPayoutResponse': payout_response.dict(),
                    'apiPayoutResponseDate': update_time,
                })
                record.modifiedDate = iso_timestamp_to_localtime(
                    payout_response.updated_at
                )
            else:
                # Nothing in this record was updated, so don't include it in the
                # bulk update procedure.
                existing_records.remove(record)

    # Save the updated data for existing records.
    SquarePayoutRecord.objects.bulk_update(
        existing_records, ['data', 'modifiedDate'], batch_size=1000
    )
    logger.info(f'Updated {len(existing_records)} existing SquarePayoutRecords.')

    # The remaining records in remaining_payouts are Square payouts for which
    # there does not yet exist a SquarePayoutRecord in the database. So, these
    # records are created.
    created_objects = [
        SquarePayoutRecord(
            payoutId=x.id,
            locationId=x.location_id,
            creationDate=iso_timestamp_to_localtime(x.created_at),
            modifiedDate=iso_timestamp_to_localtime(x.updated_at),
            data={
                'apiPayoutResponse': x.dict(),
                'apiPayoutResponseDate': update_time,
            }
        )
        for x in remaining_payouts
    ]

    SquarePayoutRecord.objects.bulk_create(created_objects)

    logger.info(f'Created {len(created_objects)} new SquarePayoutRecords.')

    # Finally, update the payout entries for any payout record that has been
    # created or updated.
    to_update_entries = SquarePayoutRecord.objects.filter(
        payoutId__in=(
            [x.payoutId for x in existing_records] +
            [x.payoutId for x in created_objects]
        )
    )

    for payout in to_update_entries:
        payout.updatePayoutEntries()

    logger.info(f'Updated payout entries for {len(to_update_entries)} payouts.')
