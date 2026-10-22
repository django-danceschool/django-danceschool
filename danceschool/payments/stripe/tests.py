'''
Tests for Stripe payment processor views.
Focused on security-sensitive paths: webhook signature handling and
redirect-target validation against open-redirect attacks.
'''
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from danceschool.core.models import Invoice


@override_settings(STRIPE_WEBHOOK_KEY='whsec_test_dummy_key')
class StripeWebhookSignatureTest(TestCase):
    '''
    Reproduces a bug at danceschool/payments/stripe/views.py:334 where the
    webhook view dereferences request.META['HTTP_STRIPE_SIGNATURE'] without
    a guard, raising KeyError (HTTP 500) when the header is absent. A
    well-behaved webhook endpoint should respond 400 for malformed
    requests so misconfigured callers see a usable error.
    '''

    def test_webhook_without_signature_header_returns_400_not_500(self):
        response = self.client.post(
            reverse('stripeWebhook'),
            data='{}',
            content_type='application/json',
        )
        self.assertEqual(
            response.status_code, 400,
            msg=(
                'Webhook without HTTP_STRIPE_SIGNATURE returned %s; '
                'expected 400 (a bare KeyError → 500 is the bug).'
            ) % response.status_code,
        )


@override_settings(STRIPE_PRIVATE_KEY='sk_test_dummy_key')
class StripeHandlerRedirectValidationTest(TestCase):
    '''
    Reproduces an open-redirect bug in handle_stripe_checkout
    (views.py:190, 192). The view reads ``successUrl`` and ``customizeUrl``
    from POST data and redirects there after a successful charge, with
    no validation that the target points back to the local site. An
    attacker who can submit the form can plant an arbitrary off-site URL
    and the application will redirect the victim's browser to it.

    Stripe SDK calls are mocked so the charge "succeeds" and execution
    reaches the redirect branch.
    '''

    EXTERNAL_URL = 'https://evil.example.com/steal'

    def setUp(self):
        self.invoice = Invoice.objects.create(
            firstName='Redirect', lastName='Victim',
            email='redir@victim.test',
            grossTotal=10, total=10,
            status=Invoice.PaymentStatus.unpaid,
        )

    def _post(self, **extra):
        post_data = {
            'stripeToken': 'tok_test_dummy',
            'stripeEmail': self.invoice.email,
            'invoice_id': str(self.invoice.id),
            'stripeAmount': '10',
        }
        post_data.update(extra)
        return self.client.post(reverse('stripeHandler'), post_data)

    def _patches(self):
        '''
        Stack the mocks needed to reach the redirect branch:
        - Stripe SDK calls returned by a successful charge.
        - Invoice.processPayment, which triggers email-template lookup
          unrelated to this test (a pre-existing dynamic_preferences
          deserialization issue in the test DB).
        '''
        fake_charge = SimpleNamespace(
            id='ch_test_dummy', amount=1000, status='succeeded',
            balance_transaction='txn_test_dummy',
        )
        fake_txn = SimpleNamespace(fee=30)
        return [
            mock.patch.multiple(
                'danceschool.payments.stripe.views.stripe',
                Charge=mock.Mock(create=mock.Mock(return_value=fake_charge)),
                BalanceTransaction=mock.Mock(retrieve=mock.Mock(return_value=fake_txn)),
                error=mock.Mock(
                    CardError=Exception, RateLimitError=Exception,
                    InvalidRequestError=Exception, AuthenticationError=Exception,
                    APIConnectionError=Exception, StripeError=Exception,
                ),
            ),
            mock.patch.object(Invoice, 'processPayment', return_value=None),
        ]

    def _post_with_patches(self, **extra):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in self._patches():
                stack.enter_context(p)
            return self._post(**extra)

    def test_external_success_url_is_rejected(self):
        response = self._post_with_patches(successUrl=self.EXTERNAL_URL)
        # Acceptable: a 302 to a SAFE URL (fallback) or any non-2xx
        # rejection. Not acceptable: redirecting to the attacker URL.
        location = response.get('Location', '')
        self.assertNotIn(
            'evil.example.com', location,
            msg=(
                'Open redirect: handle_stripe_checkout redirected to '
                'attacker-supplied successUrl %r' % location
            ),
        )

    def test_external_customize_url_is_rejected(self):
        response = self._post_with_patches(
            addSessionInfo='true',
            customizeUrl=self.EXTERNAL_URL,
        )
        location = response.get('Location', '')
        self.assertNotIn(
            'evil.example.com', location,
            msg=(
                'Open redirect: handle_stripe_checkout redirected to '
                'attacker-supplied customizeUrl %r' % location
            ),
        )

    def test_local_success_url_is_allowed(self):
        '''Regression guard: legitimate same-host URLs must still work.'''
        response = self._post_with_patches(successUrl='/registration/summary/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/registration/summary/')
