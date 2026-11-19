'''
Tests for the PayPal payment views and payment records.  Every call to PayPal
is mocked.
'''
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.template import RequestContext, Template
from django.test import RequestFactory
from django.urls import reverse
from dynamic_preferences.registries import global_preferences_registry
from paypalserversdk.exceptions.error_exception import ErrorException

from danceschool.core.constants import PAYMENT_VALIDATION_STR
from danceschool.core.models import Invoice
from danceschool.core.tests.defaults import DefaultSchoolTestCase

from .models import PaypalPaymentRecord


def money(value):
    return SimpleNamespace(value=value)


def fake_order(amount='50.00', captures=(), refunds=()):
    ''' A PayPal order as orders.get_order() returns it. '''
    return SimpleNamespace(
        id='ORDER1', status='APPROVED',
        payer=SimpleNamespace(payer_id='PAYER1', email_address='pat@example.com'),
        purchase_units=[SimpleNamespace(
            amount=money(amount),
            payments=SimpleNamespace(captures=list(captures), refunds=list(refunds)),
        )],
    )


def fake_capture(amount='50.00', status='COMPLETED', fee='1.75'):
    return SimpleNamespace(
        id='CAPTURE1', status=status, amount=money(amount),
        seller_receivable_breakdown=SimpleNamespace(paypal_fee=money(fee)),
        status_details=SimpleNamespace(reason='ECHECK') if status == 'PENDING' else None,
    )


def paypal_error(reason='Error', status=422):
    return ErrorException(reason, SimpleNamespace(status_code=status, text='{}'))


def plugin_success_page(url):
    ''' Any PayPal payment form plugin that is looked up has this success page. '''
    instance = SimpleNamespace(successPage=mock.Mock(**{'get_absolute_url.return_value': url}))
    return mock.patch(
        'danceschool.payments.paypal.views.PayNowFormModel.objects.get',
        return_value=instance,
    )


class PaypalTestCase(DefaultSchoolTestCase):

    def setUp(self):
        self.gp = global_preferences_registry.manager()
        self.gp['contact__businessEmail'] = 'school@example.com'
        # The invoice needs an item: recording PayPal's fee recalculates the
        # invoice totals from its items.
        self.invoice = Invoice.create_from_item(
            50, 'Test purchase', calculate_taxes=False,
            status=Invoice.PaymentStatus.unpaid,
        )
        self.invoice.email = 'pat@example.com'
        self.invoice.save()

        self.paypal = mock.Mock()
        self.paypal.orders.create_order.return_value.body = SimpleNamespace(
            id='ORDER1', status='CREATED',
        )
        patcher = mock.patch(
            'danceschool.payments.paypal.api_client.get_client', return_value=self.paypal,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def create(self, **data):
        post_data = {
            'invoice_id': str(self.invoice.id), 'plugin_id': '7',
            'expected_balance': '50.00', 'sourceUrl': '/register/summary/',
        }
        post_data.update(data)
        return self.client.post(reverse('createPaypalOrder'), post_data)

    def capture(self, order=None, capture=None):
        self.paypal.orders.get_order.return_value.body = order or fake_order()
        self.paypal.orders.capture_order.return_value.body = SimpleNamespace(
            payer=SimpleNamespace(payer_id='PAYER1', email_address='pat@example.com'),
            purchase_units=[SimpleNamespace(payments=SimpleNamespace(
                captures=[capture or fake_capture()],
            ))],
        )
        return self.client.post(reverse('capturePaypalOrder'), {'orderID': 'ORDER1'})

    def notices(self, subject):
        return [m for m in mail.outbox if subject in m.subject]


class CreatePaypalOrderTest(PaypalTestCase):

    def test_invoice_order(self):
        response = self.create()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'id': 'ORDER1'})

        body = self.paypal.orders.create_order.call_args.args[0]['body']
        unit = body.purchase_units[0]
        self.assertEqual(body.intent, 'CAPTURE')
        self.assertEqual(unit.amount.value, '50.00')
        self.assertEqual(unit.amount.currency_code, 'USD')
        self.assertEqual(unit.custom_id, str(self.invoice.id))

        record = PaypalPaymentRecord.objects.get()
        self.assertEqual(record.paymentId, 'ORDER1')
        self.assertEqual(record.invoice, self.invoice)
        self.invoice.refresh_from_db()
        # The invoice is not marked as authorized before the payer approves.
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.unpaid)

    def test_changed_balance_is_refused(self):
        for shown in ('45.00', '55.00'):
            response = self.create(expected_balance=shown)
            self.assertEqual(response.status_code, 400, shown)
            self.assertIn('The amount now due is $50.00', response.json()['message'])
            self.assertEqual(response.json()['redirect_url'], '/register/summary/')
        self.paypal.orders.create_order.assert_not_called()

    def test_amount_from_browser_is_ignored_for_invoice(self):
        self.create(amount='1')
        body = self.paypal.orders.create_order.call_args.args[0]['body']
        self.assertEqual(body.purchase_units[0].amount.value, '50.00')

    def test_user_is_not_taken_from_browser(self):
        other = User.objects.create_user('other', password='pass')
        self.create(user_id=other.id, submissionUser=other.id)
        self.assertIsNone(PaypalPaymentRecord.objects.get().submissionUser)

        self.client.force_login(self.superuser)
        self.paypal.orders.create_order.return_value.body = SimpleNamespace(
            id='ORDER2', status='CREATED',
        )
        self.create(user_id=other.id)
        self.assertEqual(
            PaypalPaymentRecord.objects.get(paymentId='ORDER2').submissionUser, self.superuser
        )

    def test_paid_invoice_is_not_charged(self):
        self.invoice.processPayment(amount=50, fees=0)
        response = self.create(expected_balance='0.00')
        self.assertEqual(response.status_code, 400)
        self.paypal.orders.create_order.assert_not_called()

    def test_gift_certificate(self):
        response = self.client.post(reverse('createPaypalOrder'), {
            'transaction_type': 'Gift Certificate', 'amount': '25', 'plugin_id': '7',
        })
        self.assertEqual(response.status_code, 200)
        body = self.paypal.orders.create_order.call_args.args[0]['body']
        self.assertEqual(body.purchase_units[0].amount.value, '25.00')
        self.assertTrue(self.client.session['paypal_orders']['ORDER1']['giftCertificate'])

    def test_paypal_error(self):
        self.paypal.orders.create_order.side_effect = paypal_error()
        response = self.create()
        self.assertEqual(response.status_code, 400)
        self.assertIn('Unable to start the payment', response.json()['message'])
        self.assertFalse(PaypalPaymentRecord.objects.exists())


class CapturePaypalOrderTest(PaypalTestCase):

    def setUp(self):
        super().setUp()
        self.create()

    def test_completed_payment_is_recorded(self):
        response = self.capture()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'status': 'success', 'redirect_url': reverse('registration'),
        })
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
        self.assertEqual(self.invoice.amountPaid, 50)
        self.assertAlmostEqual(self.invoice.fees, 1.75)
        record = PaypalPaymentRecord.objects.get()
        self.assertEqual(record.captureId, 'CAPTURE1')
        self.assertEqual(record.payerId, 'PAYER1')

    def test_success_page_comes_from_plugin(self):
        ''' PR #179: the success page is not taken from the browser. '''
        with plugin_success_page('/thanks/') as get:
            response = self.capture()
        get.assert_called_once_with(id=7)
        self.assertEqual(response.json()['redirect_url'], '/thanks/')

    def test_order_is_captured_once(self):
        ''' E.g. the payer's browser sends the request twice. '''
        self.capture()
        response = self.capture()
        self.assertEqual(response.json()['status'], 'success')
        self.paypal.orders.capture_order.assert_called_once()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amountPaid, 50)

    def test_changed_balance_is_not_captured(self):
        ''' The order is for 45, but staff raised the balance to 50. '''
        response = self.capture(order=fake_order(amount='45.00'))
        self.assertEqual(response.status_code, 400)
        self.assertIn('has not been charged', response.json()['message'])
        self.assertEqual(response.json()['redirect_url'], '/register/summary/')
        self.paypal.orders.capture_order.assert_not_called()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amountPaid, 0)

    def test_declined_capture(self):
        self.paypal.orders.get_order.return_value.body = fake_order()
        self.paypal.orders.capture_order.side_effect = paypal_error('INSTRUMENT_DECLINED')
        response = self.client.post(reverse('capturePaypalOrder'), {'orderID': 'ORDER1'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('not been charged', response.json()['message'])
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amountPaid, 0)

    def test_pending_capture_is_reported_to_staff(self):
        response = self.capture(capture=fake_capture(status='PENDING'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'pending')
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amountPaid, 0)
        notices = self.notices('PayPal payment pending')
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].to, ['school@example.com'])
        self.assertIn('ORDER1', notices[0].body)
        self.assertIn('CAPTURE1', notices[0].body)
        self.assertIn('ECHECK', notices[0].body)

    def test_gift_certificate_goes_to_customization(self):
        self.paypal.orders.create_order.return_value.body = SimpleNamespace(
            id='ORDER2', status='CREATED',
        )
        self.client.post(reverse('createPaypalOrder'), {
            'transaction_type': 'Gift Certificate', 'amount': '25', 'plugin_id': '7',
        })
        order = fake_order(amount='25.00')
        order.id = 'ORDER2'
        self.paypal.orders.get_order.return_value.body = order
        self.paypal.orders.capture_order.return_value.body = SimpleNamespace(
            payer=SimpleNamespace(payer_id='PAYER1', email_address='pat@example.com'),
            purchase_units=[SimpleNamespace(payments=SimpleNamespace(
                captures=[fake_capture(amount='25.00')],
            ))],
        )
        with plugin_success_page('/thanks/'):
            response = self.client.post(reverse('capturePaypalOrder'), {'orderID': 'ORDER2'})
        self.assertEqual(response.json()['redirect_url'], reverse('customizeGiftCertificate'))
        paymentSession = self.client.session[PAYMENT_VALIDATION_STR]
        self.assertEqual(paymentSession['amount'], 25)
        self.assertEqual(paymentSession['successUrl'], '/thanks/')

    def test_unknown_order(self):
        response = self.client.post(reverse('capturePaypalOrder'), {'orderID': 'NOPE'})
        self.assertEqual(response.status_code, 400)


class PaypalPaymentRecordTest(PaypalTestCase):

    def test_net_amount_paid(self):
        record = PaypalPaymentRecord.objects.create(
            paymentId='ORDER1', captureId='CAPTURE1', invoice=self.invoice,
        )
        self.paypal.orders.get_order.return_value.body = fake_order(
            captures=[fake_capture()],
            refunds=[SimpleNamespace(status='COMPLETED', amount=money('10.00'))],
        )
        self.assertEqual(record.netAmountPaid, 40)
        self.assertEqual(record.getPayerEmail(), 'pat@example.com')

    def test_refund(self):
        record = PaypalPaymentRecord.objects.create(
            paymentId='ORDER1', captureId='CAPTURE1', invoice=self.invoice,
        )
        self.paypal.payments.refund_captured_payment.return_value.body = SimpleNamespace(
            id='REFUND1', status='COMPLETED', amount=money('10.00'),
            seller_payable_breakdown=SimpleNamespace(paypal_fee=money('0.29')),
        )
        response = record.refund(10)
        options = self.paypal.payments.refund_captured_payment.call_args.args[0]
        self.assertEqual(options['capture_id'], 'CAPTURE1')
        self.assertEqual(options['body'].amount.value, '10.00')
        self.assertEqual(response, [{
            'status': 'success', 'refund_id': 'REFUND1', 'refundAmount': 10.0,
            # PayPal returns part of its fee, so the invoice fees go down.
            'fees': -0.29,
        }])

    def test_refund_error(self):
        record = PaypalPaymentRecord.objects.create(
            paymentId='ORDER1', captureId='CAPTURE1', invoice=self.invoice,
        )
        self.paypal.payments.refund_captured_payment.side_effect = paypal_error('REFUND_FAILED')
        response = record.refund(10)
        self.assertEqual(response[0]['status'], 'error')
        self.assertIn('REFUND_FAILED', response[0]['errors'][0]['message'])

    def test_payment_from_older_integration(self):
        '''
        Payments made with PayPal's v1 API cannot be looked up or refunded
        here; they must be refunded in the PayPal account.
        '''
        record = PaypalPaymentRecord.objects.create(paymentId='PAY-OLD123', invoice=self.invoice)
        self.assertIsNone(record.netAmountPaid)
        self.assertIn('PayPal account', record.api_error)
        response = record.refund(10)
        self.assertEqual(response[0]['status'], 'error')
        self.assertIn('No refund was attempted', response[0]['errors'][0]['message'])
        self.paypal.orders.get_order.assert_not_called()
        self.paypal.payments.refund_captured_payment.assert_not_called()


class PaypalTemplateTest(PaypalTestCase):

    def render(self, template, **context):
        request = RequestFactory().get('/register/summary/')
        request.user = self.superuser
        context.setdefault('instance', SimpleNamespace(id=7, defaultAmount=25))
        context.update({'paypal_client_id': 'CLIENT', 'currencyCode': 'USD'})
        return Template(
            '{% load sekizai_tags %}{% include "' + template + '" %}{% render_block "js" %}'
        ).render(RequestContext(request, context))

    def test_registration_button(self):
        html = self.render('paypal/express_checkout.html', invoice=self.invoice)
        self.assertIn('paypal.com/sdk/js?client-id=CLIENT&currency=USD', html)
        self.assertIn('params.expected_balance = "50.00"', html)
        self.assertIn('plugin_id: "7"', html)
        self.assertIn(reverse('capturePaypalOrder'), html)
        self.assertNotIn('successUrl', html)

    def test_gift_certificate_button(self):
        html = self.render('paypal/giftcertificate_form.html')
        self.assertIn("params.transaction_type = 'Gift Certificate'", html)
        self.assertIn('name="amount"', html)
        self.assertNotIn('expected_balance', html)
