import json

from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.shortcuts import resolve_url
from django.core import mail
from django.urls import reverse

from dynamic_preferences.registries import global_preferences_registry

from ..constants import REG_VALIDATION_STR
from ..models import Invoice
from .defaults import DefaultSchoolTestCase


class PaymentMismatchTest(DefaultSchoolTestCase):
    '''
    A payment that is more than the balance owed, or that was made against a
    balance that changed after the payer was shown it, is recorded, reported
    to staff by email, and returned by processPayment() so that the payment
    processor can also show a warning.
    '''

    def setUp(self):
        self.gp = global_preferences_registry.manager()
        self.gp['contact__businessEmail'] = 'school@example.com'
        self.gp['email__paymentMismatchEmailTo'] = ''
        self.invoice = Invoice.objects.create(
            firstName='Pat', lastName='Payer', email='pat@example.com',
            grossTotal=50, total=50, status=Invoice.PaymentStatus.unpaid,
        )

    def notices(self):
        return [m for m in mail.outbox if 'did not match the balance' in m.subject]

    def test_full_payment_is_not_a_mismatch(self):
        result = self.invoice.processPayment(amount=50, fees=0, expectedBalance=50)
        self.assertIsNone(result)
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
        self.assertNotIn('paymentMismatches', self.invoice.data)
        self.assertEqual(self.notices(), [])

    def test_partial_payment_without_expected_balance_is_not_a_mismatch(self):
        ''' A processor that allows partial payments does not pass expectedBalance. '''
        result = self.invoice.processPayment(amount=20, fees=0)
        self.assertIsNone(result)
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.unpaid)
        self.assertEqual(self.invoice.outstandingBalance, 30)
        self.assertEqual(self.notices(), [])

    def test_overpayment_finalizes_and_is_reported(self):
        result = self.invoice.processPayment(
            amount=55, fees=0, methodName='Test', methodTxn='TXN1',
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
        self.assertEqual(self.invoice.outstandingBalance, -5)
        self.assertEqual(result['balanceBefore'], 50)
        self.assertEqual(result['balanceAfter'], -5)
        self.assertEqual(self.invoice.data['paymentMismatches'], [result])

        notices = self.notices()
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].to, ['school@example.com'])
        self.assertIn(str(self.invoice.id), notices[0].body)
        self.assertIn('TXN1', notices[0].body)
        self.assertIn('should be refunded', notices[0].body)

    def test_payment_of_a_changed_balance_is_reported(self):
        '''
        The payer was shown 45, but staff then raised the balance to 50
        before the payment of 45 was recorded.
        '''
        result = self.invoice.processPayment(amount=45, fees=0, expectedBalance=45)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.unpaid)
        self.assertEqual(self.invoice.outstandingBalance, 5)
        self.assertEqual(result['expectedBalance'], 45)
        self.assertEqual(result['balanceAfter'], 5)

        description = self.invoice.describePaymentMismatch(result)
        self.assertIn('changed from', description)
        self.assertIn('is still owed', description)
        self.assertEqual(len(self.notices()), 1)

    def test_payment_of_a_reduced_balance_is_an_overpayment(self):
        ''' The payer was shown 55, but staff reduced the balance to 50. '''
        result = self.invoice.processPayment(amount=55, fees=0, expectedBalance=55)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
        self.assertEqual(result['balanceAfter'], -5)
        self.assertEqual(len(self.notices()), 1)

    def test_notice_goes_to_preference_address(self):
        self.gp['email__paymentMismatchEmailTo'] = 'treasurer@example.com'
        self.invoice.processPayment(amount=55, fees=0)
        self.assertEqual(self.notices()[0].to, ['treasurer@example.com'])

    def test_no_notice_when_site_emails_are_disabled(self):
        self.gp['email__disableSiteEmails'] = True
        try:
            result = self.invoice.processPayment(amount=55, fees=0)
        finally:
            self.gp['email__disableSiteEmails'] = False
        self.assertIsNotNone(result)
        self.assertEqual(self.notices(), [])

    def test_overpaid_registration_is_finalized(self):
        series = self.create_series()
        self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{
                    'item_type': 'Event', 'item_id': series.id,
                    'sku': f'EVENT_{series.id}_GENERAL', 'quantity': 1,
                }],
                'checkout': True,
            }),
            content_type='application/json',
        )
        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR]['invoice_id']
        )
        invoice.status = Invoice.PaymentStatus.unpaid
        invoice.save()
        invoice.processPayment(amount=invoice.outstandingBalance + 5, fees=0)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.PaymentStatus.paid)
        self.assertTrue(invoice.registration.final)


class InvoiceBalanceViewTest(DefaultSchoolTestCase):
    ''' The balance can be seen by anyone who can view the invoice. '''

    def setUp(self):
        self.invoice = Invoice.objects.create(
            grossTotal=50, total=50, status=Invoice.PaymentStatus.unpaid,
        )
        self.url = reverse('invoiceBalance', args=(self.invoice.id,))

    def test_validation_string_shows_balance(self):
        response = self.client.get(self.url, {'v': self.invoice.validationString})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'balance': '50.00', 'status': Invoice.PaymentStatus.unpaid,
        })

    def test_permission_shows_balance(self):
        self.client.force_login(self.superuser)
        response = self.client.get(self.url)
        self.assertEqual(response.json()['balance'], '50.00')

    def test_no_access_without_validation_string_or_permission(self):
        response = self.client.get(self.url, {'v': 'WRONG'})
        self.assertEqual(response.status_code, 302)
        self.assertIn(resolve_url(settings.LOGIN_URL), response['Location'])

        user = User.objects.create_user('noperms', password='pass')
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

        # The same permission as viewing the invoice gives access.
        user.user_permissions.add(Permission.objects.get(codename='view_all_invoices'))
        self.client.force_login(User.objects.get(id=user.id))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_same_access_as_invoice_page(self):
        ''' The balance and the invoice page agree on who may see them. '''
        for params in ({}, {'v': 'WRONG'}, {'v': self.invoice.validationString}):
            page = self.client.get(reverse('viewInvoice', args=(self.invoice.id,)), params)
            balance = self.client.get(self.url, params)
            self.assertEqual(page.status_code, balance.status_code, params)
