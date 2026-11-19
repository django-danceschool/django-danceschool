'''
Tests for the Stripe Checkout payment views.  Every call to Stripe is mocked.
'''
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

import stripe
from django.contrib.messages import get_messages
from django.core import mail
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from dynamic_preferences.registries import global_preferences_registry

from danceschool.core.constants import PAYMENT_VALIDATION_STR, getConstant
from danceschool.core.models import Invoice
from danceschool.core.tests.defaults import DefaultSchoolTestCase

from .models import StripeCharge


def fake_session(invoice, paid=True, amount=5000, **metadata):
    ''' A Checkout session as Stripe.checkout.Session.retrieve() returns it. '''
    session_metadata = {
        'invoice_id': str(invoice.id), 'plugin_id': '', 'submissionUser': '',
        'giftCertificate': '',
    }
    session_metadata.update(metadata)
    return stripe.checkout.Session.construct_from({
        'id': 'cs_test_1',
        'payment_status': 'paid' if paid else 'unpaid',
        'amount_total': amount,
        'metadata': session_metadata,
        'customer_details': {'email': 'pat@example.com'},
        'payment_intent': {
            'id': 'pi_test_1',
            'latest_charge': {
                'id': 'ch_test_1', 'amount': amount, 'status': 'succeeded',
                'balance_transaction': {'fee': 175},
            },
        },
    }, 'sk_test')


class StripeTestCase(DefaultSchoolTestCase):

    def setUp(self):
        self.gp = global_preferences_registry.manager()
        # The invoice needs an item: recording Stripe's fee recalculates the
        # invoice totals from its items.
        self.invoice = Invoice.create_from_item(
            50, 'Test purchase', calculate_taxes=False,
            status=Invoice.PaymentStatus.unpaid,
        )
        self.invoice.firstName = 'Pat'
        self.invoice.lastName = 'Payer'
        self.invoice.email = 'pat@example.com'
        self.invoice.save()

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked


class CreateCheckoutSessionTest(StripeTestCase):

    def setUp(self):
        super().setUp()
        self.create = self.patch(
            'stripe.checkout.Session.create',
            return_value=SimpleNamespace(url='https://checkout.stripe.com/c/pay/cs_test_1'),
        )

    def start(self, **data):
        post_data = {
            'invoice_id': str(self.invoice.id), 'plugin_id': '7',
            'sourceUrl': '/register/summary/',
        }
        post_data.update(data)
        return self.client.post(reverse('stripeSession'), post_data)

    def test_invoice_payment(self):
        response = self.start()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response['Location'], 'https://checkout.stripe.com/c/pay/cs_test_1')

        kwargs = self.create.call_args.kwargs
        self.assertEqual(kwargs['line_items'], [{
            'quantity': 1,
            'price_data': {
                'currency': 'usd', 'unit_amount': 5000,
                'product_data': {'name': 'Invoice Payment: %s' % self.invoice.id},
            },
        }])
        self.assertEqual(kwargs['customer_email'], 'pat@example.com')
        self.assertEqual(kwargs['metadata']['invoice_id'], str(self.invoice.id))
        self.assertEqual(kwargs['metadata']['plugin_id'], '7')
        # Stripe only stores strings in metadata.
        self.assertTrue(all(isinstance(v, str) for v in kwargs['metadata'].values()))
        self.assertEqual(
            kwargs['success_url'],
            'http://testserver%s?session_id={CHECKOUT_SESSION_ID}' % reverse('stripeReturn'),
        )
        self.assertEqual(kwargs['cancel_url'], 'http://testserver/register/summary/')

    def test_amount_from_browser_is_ignored_for_invoice(self):
        self.start(stripeAmount='1')
        unit_amount = self.create.call_args.kwargs['line_items'][0]['price_data']['unit_amount']
        self.assertEqual(unit_amount, 5000)

    def test_redirects_are_not_taken_from_browser(self):
        '''
        PR #179: the pages that the payer is sent to must not come from the
        browser, so that they cannot be used to send the payer to another site.
        '''
        self.start(
            successUrl='.evil.example/x', customizeUrl='@evil.example/x',
            sourceUrl='https://evil.example/',
        )
        kwargs = self.create.call_args.kwargs
        self.assertNotIn('evil.example', str(kwargs))
        self.assertEqual(
            kwargs['cancel_url'], 'http://testserver%s' % reverse('showRegSummary')
        )

    def test_stripe_error_returns_to_page(self):
        self.create.side_effect = stripe.error.APIConnectionError('no network')
        response = self.start()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/register/summary/')
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('Unable to start the payment' in m for m in messages))

    def test_paid_invoice_is_not_charged(self):
        self.invoice.processPayment(amount=50, fees=0)
        response = self.start()
        self.assertEqual(response.status_code, 302)
        self.create.assert_not_called()

    def test_gift_certificate(self):
        response = self.client.post(reverse('stripeSession'), {
            'stripeAmount': '25', 'transaction_type': 'Gift Certificate', 'plugin_id': '7',
        })
        self.assertEqual(response.status_code, 303)
        kwargs = self.create.call_args.kwargs
        self.assertEqual(kwargs['line_items'][0]['price_data']['unit_amount'], 2500)
        self.assertEqual(kwargs['metadata']['giftCertificate'], 'true')
        self.assertEqual(
            Invoice.objects.get(id=kwargs['metadata']['invoice_id']).outstandingBalance, 25
        )

    def test_matching_balance_starts_payment(self):
        response = self.start(expected_balance='50.00')
        self.assertEqual(response.status_code, 303)
        kwargs = self.create.call_args.kwargs
        self.assertEqual(kwargs['metadata']['expectedBalance'], '50.00')

    def test_changed_balance_is_refused(self):
        for shown in ('45.00', '55.00'):
            response = self.start(expected_balance=shown)
            self.assertEqual(response.status_code, 302, shown)
            self.assertEqual(response['Location'], '/register/summary/')
            messages = [str(m) for m in get_messages(response.wsgi_request)]
            self.assertTrue(any('The amount now due is $50.00' in m for m in messages), messages)
        self.create.assert_not_called()

    def test_session_expires_with_registration(self):
        before = timezone.now()
        self.start(expected_balance='50.00')
        expires = self.create.call_args.kwargs['expires_at']
        minutes = min(max(getConstant('registration__sessionExpiryMinutes'), 30), 24 * 60)
        self.assertAlmostEqual(
            expires, (before + timedelta(minutes=minutes)).timestamp(), delta=60
        )

    def test_form_sends_balance_shown(self):
        html = render_to_string('stripe/checkout_redirect.html', {
            'invoice': self.invoice, 'instance': SimpleNamespace(id=7),
            'request': RequestFactory().get('/register/summary/'),
        })
        self.assertIn('name="expected_balance" value="50.00"', html)
        self.assertIn('name="plugin_id" value="7"', html)
        self.assertNotIn('successUrl', html)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(reverse('stripeSession')).status_code, 405)


class StripeReturnTest(StripeTestCase):
    ''' Stripe sends the payer back to the site after they pay. '''

    def back(self, session):
        self.patch('stripe.checkout.Session.retrieve', return_value=session)
        return self.client.get(reverse('stripeReturn'), {'session_id': session.id})

    def test_payment_is_recorded(self):
        response = self.back(fake_session(self.invoice))
        self.assertRedirects(response, reverse('registration'), fetch_redirect_response=False)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
        self.assertEqual(self.invoice.amountPaid, 50)
        self.assertAlmostEqual(self.invoice.fees, 1.75)
        self.assertEqual(StripeCharge.objects.get().chargeId, 'ch_test_1')

    def test_success_page_comes_from_plugin(self):
        instance = SimpleNamespace(successPage=mock.Mock(**{'get_absolute_url.return_value': '/thanks/'}))
        with mock.patch(
            'danceschool.payments.stripe.views.StripeChargeFormModel.objects.get',
            return_value=instance,
        ) as get:
            response = self.back(fake_session(self.invoice, plugin_id='7'))
        get.assert_called_once_with(id=7)
        self.assertRedirects(response, '/thanks/', fetch_redirect_response=False)

    def test_return_and_webhook_record_payment_once(self):
        session = fake_session(self.invoice)
        self.back(session)
        self.patch('stripe.Webhook.construct_event', return_value={
            'type': 'checkout.session.completed', 'data': {'object': {'id': session.id}},
        })
        response = self.client.post(
            reverse('stripeWebhook'), data='{}', content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=1,v1=x',
        )
        self.assertEqual(response.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amountPaid, 50)
        self.assertEqual(StripeCharge.objects.count(), 1)

    def test_gift_certificate_goes_to_customization(self):
        response = self.back(fake_session(self.invoice, giftCertificate='true'))
        self.assertRedirects(
            response, reverse('customizeGiftCertificate'), fetch_redirect_response=False
        )
        paymentSession = self.client.session[PAYMENT_VALIDATION_STR]
        self.assertEqual(paymentSession['invoiceID'], str(self.invoice.id))
        self.assertEqual(paymentSession['amount'], 50)
        self.assertEqual(paymentSession['successUrl'], reverse('registration'))

    def test_payment_of_changed_balance_is_reported(self):
        '''
        The session was for the 45 that the payer was shown, but staff raised
        the balance to 50 before they paid.
        '''
        self.gp['contact__businessEmail'] = 'school@example.com'
        self.back(fake_session(self.invoice, amount=4500, expectedBalance='45.00'))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.unpaid)
        self.assertEqual(self.invoice.outstandingBalance, 5)
        self.assertEqual(len(self.invoice.data['paymentMismatches']), 1)
        self.assertEqual(
            len([m for m in mail.outbox if 'did not match the balance' in m.subject]), 1
        )

    def test_payment_still_processing(self):
        response = self.back(fake_session(self.invoice, paid=False))
        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amountPaid, 0)
        self.assertFalse(StripeCharge.objects.exists())
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('being processed' in m for m in messages))


class StripeWebhookTest(StripeTestCase):

    def send(self, event_type, session_object, **headers):
        self.patch('stripe.Webhook.construct_event', return_value={
            'type': event_type, 'data': {'object': session_object},
        })
        headers.setdefault('HTTP_STRIPE_SIGNATURE', 't=1,v1=x')
        return self.client.post(
            reverse('stripeWebhook'), data='{}', content_type='application/json',
            **headers
        )

    def test_webhook_without_signature_header_returns_400_not_500(self):
        '''
        From PR #179 (Facundo Fiorino): a request without the signature
        header is malformed, so it gets a 400 rather than a server error.
        '''
        response = self.client.post(
            reverse('stripeWebhook'), data='{}', content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(STRIPE_WEBHOOK_KEY='')
    def test_webhook_without_signing_secret_returns_400(self):
        construct = self.patch('stripe.Webhook.construct_event')
        response = self.client.post(
            reverse('stripeWebhook'), data='{}', content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=1,v1=x',
        )
        self.assertEqual(response.status_code, 400)
        construct.assert_not_called()

    def test_invalid_signature_returns_400(self):
        self.patch(
            'stripe.Webhook.construct_event',
            side_effect=stripe.error.SignatureVerificationError('bad', 'sig'),
        )
        response = self.client.post(
            reverse('stripeWebhook'), data='{}', content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=1,v1=x',
        )
        self.assertEqual(response.status_code, 400)

    def test_completed_session_is_recorded(self):
        self.patch('stripe.checkout.Session.retrieve', return_value=fake_session(self.invoice))
        response = self.send('checkout.session.completed', {'id': 'cs_test_1'})
        self.assertEqual(response.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)

    def test_session_from_elsewhere_is_ignored(self):
        ''' The Stripe account may also be used for payments not made on this site. '''
        other = stripe.checkout.Session.construct_from({
            'id': 'cs_other', 'payment_status': 'paid', 'metadata': {},
        }, 'sk_test')
        self.patch('stripe.checkout.Session.retrieve', return_value=other)
        response = self.send('checkout.session.completed', {'id': 'cs_other'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StripeCharge.objects.exists())

    def test_expired_session_marks_waiting_invoice_as_error(self):
        response = self.send('checkout.session.expired', {
            'id': 'cs_test_1', 'metadata': {'invoice_id': str(self.invoice.id)},
        })
        self.assertEqual(response.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.error)

    def test_expired_session_leaves_paid_invoice(self):
        ''' E.g. the payer left Stripe without paying, and then paid in cash. '''
        self.invoice.processPayment(amount=50, fees=0)
        self.send('checkout.session.expired', {
            'id': 'cs_test_1', 'metadata': {'invoice_id': str(self.invoice.id)},
        })
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
