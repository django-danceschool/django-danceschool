# This file has convenience methods that can be used when working directly with
# Square API objects, even if there is no associated SquarePaymentRecord.
from django.conf import settings

from square.client import Client


def getClient():
    return Client(
        access_token=getattr(settings, 'SQUARE_ACCESS_TOKEN', ''),
        environment=getattr(settings, 'SQUARE_ENVIRONMENT', 'production')
    )


def getPayments(order_id=None, order=None, client=None):
    if not client:
        client = getClient()

    if not order:
        order = client.orders.retrieve_order(order_id).body.get('order', {})

    return [
        client.payments.get_payment(x.get('id')).body.get('payment', {})
        for x in order.get('tenders', []) if x.get('id')
    ]


def getRefunds(order_id=None, order=None, client=None, payments=None):

    if not client:
        client = getClient()
    if not payments:
        payments = getPayments(order_id, order, client)

    refunds = []

    for x in payments:
        if x.get('refund_ids', []):
            for y in x['refund_ids']:
                refund_response = client.refunds.get_payment_refund(y)
                if refund_response.is_error():
                    continue
                r = refund_response.body.get('refund', {})
                if r:
                    refunds.append(r)
    return refunds


def getNetAmountPaid(**kwargs):
    payments = kwargs.pop('payments', None) or getPayments(**kwargs)

    return sum([
        x.get('amount_money', {}).get('amount', 0) / 100 -
        x.get('refunded_money', {}).get('amount', 0) / 100
        for x in payments
    ])


def getNetRefund(**kwargs):
    payments = kwargs.pop('payments', None) or getPayments(**kwargs)

    return sum([
        x.get('refunded_money', {}).get('amount', 0) / 100
        for x in payments
    ])

def getNetFees(**kwargs):

    # Note that we pop refunds before payments so there is no need to look up
    # payments twice.
    refunds = kwargs.pop('refunds', None) or getRefunds(**kwargs)
    payments = kwargs.pop('payments', None) or getPayments(**kwargs)

    fees = 0

    for x in payments:
        fees += sum([
            y.get('amount_money', {}).get('amount', 0) / 100
            for y in x.get('processing_fee', [])
        ])
    for r in refunds:
        fees += sum([
            f.get('amount_money', {}).get('amount', 0) / 100
            for f in r.get('processing_fee', [])
        ])

    return fees


def getNetRevenue(**kwargs):
    return getNetAmountPaid(**kwargs) - getNetFees(**kwargs)
