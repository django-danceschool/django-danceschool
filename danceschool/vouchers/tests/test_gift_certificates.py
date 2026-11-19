from django.urls import reverse

from danceschool.core.constants import PAYMENT_VALIDATION_STR
from danceschool.core.models import Invoice
from danceschool.core.tests.defaults import DefaultSchoolTestCase


class GiftCertificateCustomizeViewSessionKeysTest(DefaultSchoolTestCase):
    '''
    Regression coverage for GiftCertificateCustomizeView's session-key lookup.

    All three payment providers (Stripe, PayPal, Square) write the
    PAYMENT_VALIDATION_STR session dict using camelCase keys: 'invoiceID',
    'amount', 'successUrl'. The customize view must read those same keys; if
    it looks up snake_case keys instead, every successful gift certificate
    purchase 400s on the post-payment redirect and no Voucher is ever issued
    (the customer is charged with nothing to show for it).
    '''

    def _set_payment_session(self, invoice, amount, success_url='/done/'):
        session = self.client.session
        session[PAYMENT_VALIDATION_STR] = {
            'invoiceID': str(invoice.id),
            'amount': amount,
            'successUrl': success_url,
        }
        session.save()

    def test_paid_invoice_with_camelcase_session_keys_renders_form(self):
        '''
        With the camelCase keys the payment views actually write, the
        customize view must locate the paid invoice and render the form
        (200), not return 400 'Invalid invoice information passed.'
        '''
        invoice = Invoice.objects.create(
            grossTotal=10, total=10, amountPaid=10,
            status=Invoice.PaymentStatus.paid,
        )
        self._set_payment_session(invoice, amount=10)

        response = self.client.get(reverse('customizeGiftCertificate'))

        self.assertEqual(response.status_code, 200)

    def test_success_url_must_be_on_this_site(self):
        '''
        The payment processor apps look the success URL in the session up on
        the server (PR #179), but another payment processor app could take it
        from the browser, so a page on another site is replaced by the
        registration page.
        '''
        invoice = Invoice.objects.create(
            grossTotal=10, total=10, amountPaid=10,
            status=Invoice.PaymentStatus.paid,
        )
        for url, expected in [
            ('/done/', '/done/'),
            ('https://evil.example/x', reverse('registration')),
            ('//evil.example/x', reverse('registration')),
        ]:
            self._set_payment_session(invoice, amount=10, success_url=url)
            response = self.client.get(reverse('customizeGiftCertificate'))
            self.assertEqual(response.context_data['view'].success_url, expected, url)

    def test_unpaid_invoice_returns_400(self):
        '''
        Sanity-check the second guard: even with correct keys, an unpaid
        invoice must still 400 with 'Passed invoice is not paid.'
        '''
        invoice = Invoice.objects.create(
            grossTotal=10, total=10, amountPaid=0,
            status=Invoice.PaymentStatus.unpaid,
        )
        self._set_payment_session(invoice, amount=10)

        response = self.client.get(reverse('customizeGiftCertificate'))

        self.assertEqual(response.status_code, 400)
