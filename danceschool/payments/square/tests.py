import json
from base64 import b64encode
from types import SimpleNamespace
from unittest import mock

import httpx
from django.contrib.auth.context_processors import PermWrapper
from django.contrib.messages import get_messages
from django.core import mail
from django.template import RequestContext, Template
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import reverse
from dynamic_preferences.registries import global_preferences_registry
from square.core.api_error import ApiError

from danceschool.core.constants import PAYMENT_VALIDATION_STR, REFUND_VALIDATION_STR
from danceschool.core.models import Invoice
from danceschool.core.tests.defaults import DefaultSchoolTestCase

from .api_client import clear_square_failure, square_api_status
from .models import SquarePaymentRecord, SquarePayoutEntry, SquarePayoutRecord


UNAUTHORIZED = {'errors': [{
    'category': 'AUTHENTICATION_ERROR', 'code': 'UNAUTHORIZED',
    'detail': 'This request could not be authorized.',
}]}
NOT_FOUND = {'errors': [{'category': 'INVALID_REQUEST_ERROR', 'code': 'NOT_FOUND', 'detail': 'Not found.'}]}
PAYMENT = {
    'id': 'PAYMENT_CACHED', 'amount_money': {'amount': 2500, 'currency': 'USD'},
    'processing_fee': [{'amount_money': {'amount': 100}}],
}


def plugin_success_page(url):
    ''' Any Square payment form plugin that is looked up has this success page. '''
    instance = SimpleNamespace(successPage=mock.Mock(**{'get_absolute_url.return_value': url}))
    return mock.patch(
        'danceschool.payments.square.views.SquareCheckoutFormModel.objects.get',
        return_value=instance,
    )


def fake_client(get=None, refund=None):
    '''
    A stand-in for the Square client.  get and refund are what
    payments.get() and refunds.refund_payment() raise or return (as a
    response whose .dict() is that value).
    '''
    client = mock.Mock()
    for method, result in ((client.payments.get, get), (client.refunds.refund_payment, refund)):
        if isinstance(result, Exception):
            method.side_effect = result
        else:
            method.return_value.dict.return_value = result or {}
    return client


@override_settings(SQUARE_ACCESS_TOKEN='test-token')
class SquareAPIUnavailableTest(DefaultSchoolTestCase):
    '''
    Without working Square credentials (a test site, or a Square outage),
    pages that show Square payments must still render, using the data saved
    locally, and operations that need Square must report why they failed.
    '''

    def setUp(self):
        clear_square_failure()
        self.addCleanup(clear_square_failure)
        self.invoice = Invoice.objects.create(firstName='Pat', lastName='Payer', total=25, grossTotal=25)
        self.cached = SquarePaymentRecord.objects.create(
            invoice=self.invoice, paymentId='PAYMENT_CACHED', locationId='LOC',
            data={'apiPaymentResponse': PAYMENT},
        )
        self.uncached = SquarePaymentRecord.objects.create(paymentId='PAYMENT_UNCACHED', locationId='LOC')

    def use_client(self, client):
        patcher = mock.patch('danceschool.payments.square.models.api_client', client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def fresh(self, record):
        ''' Reload a record, so that it picks up the patched client. '''
        return SquarePaymentRecord.objects.get(pk=record.pk)

    def test_uncached_amounts_are_none_when_the_api_fails(self):
        self.use_client(fake_client(get=ApiError(status_code=401, body=UNAUTHORIZED)))
        record = self.fresh(self.uncached)
        self.assertIsNone(record.netAmountPaid)
        self.assertIn('UNAUTHORIZED', record.api_error)
        self.assertIsNone(record.netFees)
        self.assertIsNone(record.netRevenue)
        self.assertEqual(record.orderLineItems, [])
        ok, reason = square_api_status()
        self.assertFalse(ok)
        self.assertIn('UNAUTHORIZED', reason)

    def test_cached_amounts_need_no_api(self):
        client = self.use_client(fake_client(get=ApiError(status_code=401, body=UNAUTHORIZED)))
        record = self.fresh(self.cached)
        self.assertEqual(record.netAmountPaid, 25)
        self.assertEqual(record.netFees, 1)
        self.assertEqual(record.netRevenue, 24)
        client.payments.get.assert_not_called()

    def test_one_failure_pauses_further_calls(self):
        client = self.use_client(fake_client(get=ApiError(status_code=401, body=UNAUTHORIZED)))
        other = SquarePaymentRecord.objects.create(paymentId='PAYMENT_OTHER', locationId='LOC')
        self.assertIsNone(self.fresh(self.uncached).netAmountPaid)
        record = self.fresh(other)
        self.assertIsNone(record.netAmountPaid)
        self.assertEqual(client.payments.get.call_count, 1)
        self.assertIn('UNAUTHORIZED', record.api_error)

    def test_unknown_payment_does_not_pause_the_api(self):
        self.use_client(fake_client(get=ApiError(status_code=404, body=NOT_FOUND)))
        record = self.fresh(self.uncached)
        self.assertIsNone(record.netAmountPaid)
        self.assertIn('NOT_FOUND', record.api_error)
        self.assertTrue(square_api_status()[0])

    def test_no_connection(self):
        self.use_client(fake_client(get=httpx.ConnectError('no network')))
        record = self.fresh(self.uncached)
        self.assertIsNone(record.netAmountPaid)
        self.assertIn('ConnectError', record.api_error)
        self.assertFalse(square_api_status()[0])

    @override_settings(SQUARE_ACCESS_TOKEN=None)
    def test_no_credentials_means_no_calls(self):
        client = self.use_client(fake_client(get=ApiError(status_code=401, body=UNAUTHORIZED)))
        record = self.fresh(self.uncached)
        self.assertIsNone(record.netAmountPaid)
        self.assertIn('SQUARE_ACCESS_TOKEN', record.api_error)
        client.payments.get.assert_not_called()

    def test_errors_still_raise_for_operations(self):
        self.use_client(fake_client(get=ApiError(status_code=401, body=UNAUTHORIZED)))
        with self.assertRaises(ApiError):
            self.fresh(self.uncached).getPayment()

    def test_admin_pages_render_with_a_warning(self):
        self.use_client(fake_client(get=ApiError(status_code=401, body=UNAUTHORIZED)))
        payout = SquarePayoutRecord.objects.create(
            payoutId='PAYOUT1', locationId='LOC', creationDate=self.invoice.creationDate,
            modifiedDate=self.invoice.creationDate,
        )
        SquarePayoutEntry.objects.create(entryId='ENTRY1', payout=payout, paymentRecord=self.uncached)
        self.client.force_login(self.superuser)
        # The first page load finds out that the API is unavailable...
        self.assertEqual(self.client.get(reverse('admin:square_squarepaymentrecord_changelist')).status_code, 200)
        # ...and from then on every page says so.
        for url in (
            reverse('admin:square_squarepaymentrecord_changelist'),
            reverse('admin:square_squarepaymentrecord_change', args=(self.uncached.pk,)),
            reverse('admin:square_squarepaymentrecord_change', args=(self.cached.pk,)),
            reverse('admin:square_squarepayoutrecord_changelist'),
            reverse('admin:square_squarepayoutrecord_change', args=(payout.pk,)),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertContains(response, 'Square API unavailable (UNAUTHORIZED')

    def test_refund_reports_api_failure(self):
        self.use_client(fake_client(get=ApiError(status_code=401, body=UNAUTHORIZED)))
        response = self.fresh(self.cached).refund(5)
        self.assertEqual(response[0]['status'], 'error')
        self.assertIn('UNAUTHORIZED', response[0]['errors'][0]['message'])
        json.dumps(response)

    def test_refund_processor_errors_are_plain_data(self):
        self.use_client(fake_client(
            get={'payment': PAYMENT}, refund=ApiError(status_code=400, body=NOT_FOUND),
        ))
        with mock.patch('danceschool.payments.square.models.updateSquareFees') as task:
            response = self.fresh(self.cached).refund(5)
        self.assertEqual(response, [{'status': 'error', 'errors': [{'code': 'NOT_FOUND', 'message': 'Not found.'}]}])
        task.schedule.assert_not_called()

    def test_successful_refund_schedules_fee_update(self):
        self.use_client(fake_client(
            get={'payment': PAYMENT}, refund={'refund': {'id': 'REFUND1', 'amount_money': {'amount': 500}}},
        ))
        with mock.patch('danceschool.payments.square.models.updateSquareFees') as task:
            response = self.fresh(self.cached).refund(5)
        self.assertEqual(response[0]['status'], 'success')
        self.assertEqual(response[0]['refundAmount'], 5)
        task.schedule.assert_called_once_with(args=(self.cached.pk,), delay=60)

    def test_create_invoice_needs_payment_data(self):
        self.use_client(fake_client(get=ApiError(status_code=401, body=UNAUTHORIZED)))
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('viewOrCreatePaymentInvoice', args=(self.uncached.pk,)))
        self.assertRedirects(response, reverse('admin:square_squarepaymentrecord_changelist'))
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('Cannot create an invoice' in m and 'UNAUTHORIZED' in m for m in messages))

    def test_created_invoice_records_square_refund(self):
        '''
        A refund made in Square before the invoice is created is recorded as
        a refund (not as an adjustment), along with the refunds that payment
        processors report, so that check_refunds finds that they match.
        '''
        self.use_client(fake_client(get=ApiError(status_code=401, body=UNAUTHORIZED)))
        record = SquarePaymentRecord.objects.create(
            paymentId='PAYMENT_REFUNDED', locationId='LOC',
            data={'apiPaymentResponse': dict(
                PAYMENT, id='PAYMENT_REFUNDED', refunded_money={'amount': 500},
            )},
        )
        self.client.force_login(self.superuser)
        self.client.post(
            reverse('viewOrCreatePaymentInvoice', args=(record.pk,)), {'comments': ''}
        )
        record.refresh_from_db()
        invoice = record.invoice
        self.assertIsNotNone(invoice)
        self.assertAlmostEqual(invoice.refunds, 5)
        self.assertAlmostEqual(invoice.adjustments, 0)
        self.assertAlmostEqual(invoice.invoiceitem_set.get().refunds, 5)
        self.assertEqual(
            [(x['status'], x['refundAmount']) for x in invoice.data['refunds']],
            [('success', 5)],
        )

    def confirm_refund(self, record):
        record.invoice = self.invoice
        record.save()
        self.client.force_login(self.superuser)
        session = self.client.session
        session[REFUND_VALIDATION_STR] = {'form_data': {
            'id': str(self.invoice.id), 'total_refund_amount': 10, 'initial_refund_amount': 0,
        }}
        session.save()
        return self.client.get(reverse('refundConfirmation') + '?confirmed=true')

    def test_refund_view_does_not_guess_an_unknown_amount(self):
        # Only the uncached payment: its amount cannot be determined.
        self.cached.delete()
        client = self.use_client(fake_client(get=ApiError(status_code=401, body=UNAUTHORIZED)))
        response = self.confirm_refund(self.uncached)
        self.assertEqual(response.status_code, 302)
        client.refunds.refund_payment.assert_not_called()
        self.invoice.refresh_from_db()
        failed = self.invoice.data['refunds'][-1]
        self.assertEqual(failed['status'], 'error')
        self.assertIn('no refund was attempted', failed['errorMessage'])
        self.assertIn('UNAUTHORIZED', failed['errorMessage'])
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('no refund was attempted' in m for m in messages))

    def test_refund_view_shows_processor_errors(self):
        self.use_client(fake_client(get=ApiError(status_code=401, body=UNAUTHORIZED)))
        response = self.confirm_refund(self.cached)
        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        failed = self.invoice.data['refunds'][-1]
        self.assertEqual(failed['status'], 'error')
        self.assertIn('Unable to retrieve the Square payment', failed['errorMessage'])
        self.assertIn('UNAUTHORIZED', failed['errorMessage'])


class SquareCheckoutBalanceTest(DefaultSchoolTestCase):
    '''
    A Square Checkout payment on an invoice is refused, without charging the
    card, if the balance is not the one that the payer was shown.
    '''

    def setUp(self):
        self.invoice = Invoice.objects.create(
            firstName='Pat', lastName='Payer', email='pat@example.com',
            grossTotal=50, total=50, status=Invoice.PaymentStatus.unpaid,
        )
        self.square = mock.Mock()
        self.square.payments.create.return_value.dict.return_value = {'payment': {
            'id': 'PAYMENT1', 'order_id': 'ORDER1', 'location_id': 'LOC',
        }}
        for target, value in (
            ('danceschool.payments.square.views.api_client', self.square),
            ('danceschool.payments.square.views.updateSquareFees', mock.Mock()),
        ):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def pay(self, **data):
        details = {
            'invoice_id': str(self.invoice.id), 'sourceId': 'cnon:card',
            'sourceUrl': '/register/summary/',
        }
        details.update(data)
        return self.client.post(
            reverse('processSquarePayment'), data=json.dumps(details),
            content_type='application/json',
        )

    def assert_refused(self, response, redirect_url='/register/summary/'):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'error')
        self.assertIn('has not been charged', response.json()['message'])
        self.assertEqual(response.json()['redirect_url'], redirect_url)
        self.square.payments.create.assert_not_called()
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('The amount now due is' in m for m in messages))

    def test_matching_balance_is_charged(self):
        response = self.pay(expected_balance='50.00')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.square.payments.create.call_args.kwargs['amount_money']['amount'], 5000
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
        self.assertNotIn('paymentMismatches', self.invoice.data)

    def test_increased_balance_is_refused(self):
        ''' The payer was shown 45, but the balance is now 50. '''
        self.assert_refused(self.pay(expected_balance='45.00'))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amountPaid, 0)

    def test_reduced_balance_is_refused(self):
        ''' The payer was shown 55, but staff reduced the balance to 50. '''
        self.assert_refused(self.pay(expected_balance='55.00'))

    def test_paid_invoice_is_not_charged_again(self):
        ''' E.g. the payment form was submitted a second time. '''
        self.assertEqual(self.pay(expected_balance='50.00').status_code, 302)
        self.square.payments.create.reset_mock()
        self.assert_refused(self.pay(expected_balance='50.00', idempotency_key='second'))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amountPaid, 50)

    def test_refusal_does_not_redirect_offsite(self):
        self.assert_refused(
            self.pay(expected_balance='45.00', sourceUrl='https://example.org/'),
            redirect_url=reverse('showRegSummary'),
        )

    def test_payment_without_expected_balance_is_charged(self):
        ''' A page that was loaded before this change does not send one. '''
        self.assertEqual(self.pay().status_code, 302)
        self.square.payments.create.assert_called_once()

    def test_gift_certificate_is_unaffected(self):
        response = self.client.post(
            reverse('processSquarePayment'), data=json.dumps({
                'sourceId': 'cnon:card', 'transaction_type': 'Gift Certificate',
                'amount': '25',
            }), content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.square.payments.create.call_args.kwargs['amount_money']['amount'], 2500
        )

    def test_redirects_are_not_taken_from_browser(self):
        ''' PR #179: the success page comes from the plugin, on the server. '''
        with plugin_success_page('/thanks/') as get:
            response = self.pay(
                expected_balance='50.00', plugin_id='7',
                successUrl='https://evil.example/x', finalSuccessUrl='https://evil.example/y',
                addSessionInfo=True,
            )
        get.assert_called_once_with(id=7)
        self.assertRedirects(response, '/thanks/', fetch_redirect_response=False)
        self.assertNotIn(PAYMENT_VALIDATION_STR, self.client.session)

    def test_without_plugin_success_page(self):
        response = self.pay(expected_balance='50.00', successUrl='https://evil.example/x')
        self.assertRedirects(response, reverse('registration'), fetch_redirect_response=False)

    def test_gift_certificate_goes_to_customization(self):
        with plugin_success_page('/thanks/'):
            response = self.client.post(
                reverse('processSquarePayment'), data=json.dumps({
                    'sourceId': 'cnon:card', 'transaction_type': 'Gift Certificate',
                    'amount': '25', 'plugin_id': '7',
                    'successUrl': 'https://evil.example/x',
                    'finalSuccessUrl': 'https://evil.example/y',
                }), content_type='application/json',
            )
        self.assertRedirects(
            response, reverse('customizeGiftCertificate'), fetch_redirect_response=False
        )
        paymentSession = self.client.session[PAYMENT_VALIDATION_STR]
        self.assertEqual(paymentSession['successUrl'], '/thanks/')
        self.assertEqual(paymentSession['amount'], 25)

    def test_checkout_form_sends_balance_shown(self):
        request = RequestFactory().get('/register/summary/')
        request.user = self.superuser
        # The script is added to the page's "js" block.
        html = Template(
            '{% load sekizai_tags %}{% include "square/checkout.html" %}'
            '{% render_block "js" %}'
        ).render(RequestContext(request, {
            'user': self.superuser, 'invoice': self.invoice, 'instance': None,
        }))
        self.assertIn('expected_balance: "50.00"', html)
        self.assertIn('sourceUrl: "/register/summary/"', html)


class SquarePointOfSaleBalanceTest(DefaultSchoolTestCase):
    '''
    The Square app charges the balance that the page was loaded with before
    the site hears about the payment.  If that no longer matches the balance,
    the payment is recorded, staff are emailed, and the staff member who took
    it is warned.
    '''

    def setUp(self):
        self.gp = global_preferences_registry.manager()
        self.gp['contact__businessEmail'] = 'school@example.com'
        self.invoice = Invoice.objects.create(
            firstName='Pat', lastName='Payer', email='pat@example.com',
            grossTotal=50, total=50, status=Invoice.PaymentStatus.unpaid,
        )
        self.square = mock.Mock()
        for target, value in (
            ('danceschool.payments.square.views.api_client', self.square),
            ('danceschool.payments.square.views.updateSquareFees', mock.Mock()),
        ):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client.force_login(self.superuser)

    def callback(self, charged, **metadata):
        ''' The Square app (on Android) returns after charging this amount. '''
        payment = mock.Mock(order_id='CLIENT1')
        payment.dict.return_value = {
            'id': 'PAYMENT1', 'order_id': 'CLIENT1', 'location_id': 'LOC',
            'amount_money': {'amount': round(charged * 100)},
        }
        self.square.payments.list.return_value = [payment]

        state = {'invoice': str(self.invoice.id), 'sourceUrl': '/register/summary/'}
        state.update(metadata)
        response = self.client.get(reverse('processSquarePointOfSale'), {
            'com.squareup.pos.CLIENT_TRANSACTION_ID': 'CLIENT1',
            'com.squareup.pos.REQUEST_METADATA': b64encode(json.dumps(state).encode()).decode(),
        })
        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        return [str(m) for m in get_messages(response.wsgi_request)]

    def notices(self):
        return [m for m in mail.outbox if 'did not match the balance' in m.subject]

    def test_matching_payment(self):
        messages = self.callback(50, expectedBalance='50.00')
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
        self.assertEqual(self.invoice.amountPaid, 50)
        self.assertEqual(messages, [])
        self.assertEqual(self.notices(), [])

    def test_balance_raised_after_sending_to_app(self):
        messages = self.callback(45, expectedBalance='45.00')
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.unpaid)
        self.assertEqual(self.invoice.outstandingBalance, 5)
        self.assertEqual(len(self.invoice.data['paymentMismatches']), 1)
        self.assertTrue(any('is still owed' in m for m in messages), messages)
        self.assertEqual(len(self.notices()), 1)

    def test_balance_reduced_after_sending_to_app(self):
        messages = self.callback(55, expectedBalance='55.00')
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
        self.assertTrue(any('should be refunded' in m for m in messages), messages)
        self.assertEqual(len(self.notices()), 1)

    def test_page_without_expected_balance(self):
        ''' A page loaded before this change sends no balance. '''
        messages = self.callback(50)
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
        self.assertEqual(messages, [])

    def test_callback_repeated_is_not_reported_again(self):
        self.callback(45, expectedBalance='45.00')
        messages = self.callback(45, expectedBalance='45.00')
        # The warning from the first callback has not been displayed yet
        # (the redirect is not followed), but no second one is added.
        self.assertEqual(len([m for m in messages if 'is still owed' in m]), 1)
        self.assertEqual(self.invoice.amountPaid, 45)
        self.assertEqual(len(self.notices()), 1)

    def test_success_page_from_plugin(self):
        ''' PR #179: the success page comes from the plugin, not the metadata. '''
        with plugin_success_page('/thanks/'):
            payment = mock.Mock(order_id='CLIENT1')
            payment.dict.return_value = {
                'id': 'PAYMENT1', 'order_id': 'CLIENT1', 'location_id': 'LOC',
                'amount_money': {'amount': 5000},
            }
            self.square.payments.list.return_value = [payment]
            state = {
                'invoice': str(self.invoice.id), 'plugin_id': '7',
                'successUrl': 'https://evil.example/x',
            }
            response = self.client.get(reverse('processSquarePointOfSale'), {
                'com.squareup.pos.CLIENT_TRANSACTION_ID': 'CLIENT1',
                'com.squareup.pos.REQUEST_METADATA': b64encode(json.dumps(state).encode()).decode(),
            })
        self.assertRedirects(response, '/thanks/', fetch_redirect_response=False)

    def test_error_returns_only_to_this_site(self):
        state = {'invoice': str(self.invoice.id), 'sourceUrl': 'https://evil.example/x'}
        response = self.client.get(reverse('processSquarePointOfSale'), {
            'com.squareup.pos.ERROR_CODE': 'com.squareup.pos.ERROR_TRANSACTION_CANCELED',
            'com.squareup.pos.REQUEST_METADATA': b64encode(json.dumps(state).encode()).decode(),
        })
        self.assertRedirects(response, reverse('showRegSummary'), fetch_redirect_response=False)

    def test_button_checks_balance(self):
        request = RequestFactory().get('/register/summary/')
        request.user = self.superuser
        html = Template(
            '{% load sekizai_tags %}{% include "square/point_of_sale.html" %}'
            '{% render_block "js" %}'
        ).render(RequestContext(request, {
            'user': self.superuser, 'perms': PermWrapper(self.superuser),
            'invoice': self.invoice, 'payAtDoor': True, 'instance': None,
            'currencyCode': 'USD', 'returnUrl': 'https://example.com/square/pos/',
            'squareApplicationId': 'test-app-id',
        }))
        self.assertIn('expectedBalance: "50.00"', html)
        self.assertIn('{}?v={}'.format(
            reverse('invoiceBalance', args=(self.invoice.id,)),
            self.invoice.validationString,
        ), html)


class SquarePointOfSaleTemplateTest(DefaultSchoolTestCase):
    '''
    The point-of-sale button must render based on the session-level payAtDoor
    flag, not on a Registration object (which does not exist for carts that
    contain only merchandise).
    '''

    def _render(self, **extra):
        request = RequestFactory().get('/register/summary/')
        request.user = self.superuser
        context = {
            'request': request,
            'user': self.superuser,
            'perms': PermWrapper(self.superuser),
            'currencyCode': 'USD',
            'instance': None,
            'returnUrl': 'https://example.com/square/pos/',
            'squareApplicationId': 'test-app-id',
        }
        context.update(extra)
        return render_to_string('square/point_of_sale.html', context, request=request)

    def test_button_renders_without_registration(self):
        '''Merchandise-only carts have no Registration but should show the button.'''
        html = self._render(payAtDoor=True, registration=None)
        self.assertIn('square-pos-button', html)

    def test_button_renders_with_registration(self):
        html = self._render(payAtDoor=True, registration=object())
        self.assertIn('square-pos-button', html)

    def test_button_hidden_when_not_pay_at_door(self):
        html = self._render(payAtDoor=False, registration=None)
        self.assertNotIn('square-pos-button', html)
