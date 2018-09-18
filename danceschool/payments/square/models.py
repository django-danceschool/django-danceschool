from django.db import models
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from cms.models.pluginmodel import CMSPlugin
from cms.models.fields import PageField

import logging
from squareconnect.rest import ApiException
from squareconnect.apis.transactions_api import TransactionsApi
import uuid

from danceschool.core.models import PaymentRecord
from .tasks import updateSquareFees


# Define logger for this file
logger = logging.getLogger(__name__)


class SquarePaymentRecord(PaymentRecord):
    '''
    Keeps a local record of Square transactions so that they can be looked up
    using the REST API.
    '''

    transactionId = models.CharField(_('Square Transaction ID'),max_length=50,unique=True)
    locationId = models.CharField(_('Square Location ID'),max_length=50)
    payerEmail = models.EmailField(_('Associated email'), null=True, blank=True)

    @property
    def methodName(self):
        return 'Square Checkout'

    @property
    def refundable(self):
        return True

    @property
    def recordId(self):
        '''
        Payment methods should override this if they keep their own unique identifiers.
        '''
        return self.transactionId

    @property
    def netAmountPaid(self):
        payment = self.getPayment()
        return sum([x.amount_money.amount / 100 for x in payment.tenders or []]) - \
            sum([x.amount_money.amount / 100 for x in payment.refunds or []])

    @property
    def netFees(self):
        payment = self.getPayment()
        return sum([x.processing_fee_money.amount / 100 for x in payment.tenders or []]) - \
            sum([x.processing_fee_money.amount / 100 for x in payment.refunds or []])

    def getPayment(self):
        api_instance = TransactionsApi()
        api_instance.api_client.configuration.access_token = getattr(settings,'SQUARE_ACCESS_TOKEN','')

        try:
            response = api_instance.retrieve_transaction(
                location_id=self.locationId,
                transaction_id=self.transactionId
            )
            if response.errors:
                logger.error('Unable to retrieve Square transaction from record.')
                return None
        except ApiException as e:
            logger.error('Unable to retrieve Square transaction from record.')
            return None
        return response.transaction

    def getPayerEmail(self):
        return self.payerEmail

    def refund(self, amount=None):
        api_instance = TransactionsApi()
        transaction = self.getPayment()

        # For both partial and full refunds, we loop through the tenders and refund
        # them as much as possible until we've refunded all that we want to refund.
        if not amount:
            amount = sum([x.amount_money.amount / 100 for x in transaction.tenders or []]) - \
                sum([x.amount_money.amount / 100 for x in transaction.refunds or []])

        refundData = []
        print('Beginning refund process.')

        remains_to_refund = amount
        tender_index = 0
        while remains_to_refund > 0:
            idempotency_key = str(uuid.uuid1())

            this_tender = transaction.tenders[tender_index]
            this_tender_refundamount = sum([
                x.amount_money.amount / 100 for x in transaction.refunds or [] if x.tender_id == this_tender.id
            ])

            to_refund = min(
                this_tender.amount_money.amount - this_tender_refundamount,
                remains_to_refund
            )

            body = {
                'idempotency_key': idempotency_key,
                'tender_id': this_tender.id,
                'amount_money': {'amount': int(to_refund * 100), 'currency': this_tender.amount_money.currency}
            }

            try:
                response = api_instance.create_refund(
                    location_id=self.locationId,transaction_id=self.transactionId,body=body
                )
                if response.errors:
                    logger.error('Error in providing Square refund: %s' % response.errors)
                    refundData.append({'status': 'error', 'status': response.errors})
                    break
            except ApiException:
                logger.error('Error in providing Square refund.')
                refundData.append({'status': 'error', 'errors': response.errors})
                break

            print('Refund was successful?  Data is: %s' % response)

            # Note that fees are often 0 or missing here, but we enqueue the task
            # retrieve and update them afterward.
            refundData.append({
                'status': 'success',
                'refund_id': response.refund.id,
                'refundAmount': float(response.refund.amount_money.amount) / 100,
                'fees': float(getattr(getattr(response.refund,'processing_fee_money',None),'amount',0)) / 100,
            })

            remains_to_refund -= to_refund
            tender_index += 1

            # Once the refund process is complete, fees will be calculated,
            # so schedule a task to get them and update records one minute
            # in the future.
            updateSquareFees.schedule(args=(self,), delay=60)

        print('Ready to return: %s' % refundData)
        return refundData

    class Meta:
        permissions = (
            ('handle_pos_payments',_('Has access to point-of-sale payment functionality')),
        )
        verbose_name = _('Square payment record')
        verbose_name_plural = _('Payment records')


class SquareCheckoutFormModel(CMSPlugin):
    ''' This model holds options for instances of the SquarePaymentFormPlugin '''

    successPage = PageField(verbose_name=_('Success Page'),help_text=_('When the user returns to the site after a successful transaction, send them to this page.'),related_name='successPageForSquare')
    defaultAmount = models.FloatField(verbose_name=_('Default amount'),help_text=_('The initial value for gift certificate forms.'),default=0)

    def get_short_description(self):
        return self.plugin_type or self.id
