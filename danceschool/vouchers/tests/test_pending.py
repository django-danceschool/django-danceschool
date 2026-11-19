import json

from django.urls import reverse

from danceschool.core.constants import updateConstant
from danceschool.core.models import Customer

from ..models import CustomerVoucher, Voucher
from .base import BaseVouchersTest


PENDING_TEXT = 'this amount is not final'


class VoucherPendingNoteTest(BaseVouchersTest):
    '''
    The amount shown for a voucher that depends on customer information (who
    is paying, or who each registration is for) is marked as not final until
    that information has been entered.
    '''

    def setUp(self):
        updateConstant('vouchers__enableVouchers', True)
        self.series = self.create_series(classDescription=self.levelOneClassDescription)
        self.other_series = self.create_series(
            classDescription=self.levelTwoClassDescription
        )
        self.first_time = Voucher.objects.create(
            voucherId='NEWBIE', name='New Customer Voucher', originalAmount=10,
            forFirstTimeCustomersOnly=True,
        )
        self.plain = Voucher.objects.create(
            voucherId='PLAIN', name='Plain Voucher', originalAmount=10,
        )

    def cart(self, voucher, *events, checkout=False):
        return self.client.post(
            reverse('cart'), content_type='application/json',
            data=json.dumps({
                'items': [
                    {
                        'item_type': 'Event', 'item_id': e.id,
                        'sku': 'EVENT_%s_GENERAL' % e.id, 'quantity': 1,
                    } for e in events
                ],
                'checkout': checkout, 'discount_code': voucher.voucherId,
            }),
        )

    def test_cart_previews(self):
        for voucher, pending in [(self.first_time, True), (self.plain, False)]:
            self.new_session()
            response = self.cart(voucher, self.series)
            self.assertEqual(
                response.json()['voucher_preview']['customer_pending'], pending,
                msg=voucher.voucherId
            )

            response = self.client.get(reverse('cartSummary'))
            self.assertEqual(
                response.context_data['voucher_preview']['customer_pending'], pending,
                msg=voucher.voucherId
            )
            if pending:
                self.assertContains(response, PENDING_TEXT)
            else:
                self.assertNotContains(response, PENDING_TEXT)

    def test_customer_information_page(self):
        for voucher, pending in [(self.first_time, True), (self.plain, False)]:
            self.new_session()
            self.cart(voucher, self.series, checkout=True)

            response = self.client.get(reverse('getStudentInfo'))

            self.assertEqual(
                response.context_data['voucher']['customerPending'], pending,
                msg=voucher.voucherId
            )
            if pending:
                self.assertContains(response, PENDING_TEXT)
            else:
                self.assertNotContains(response, PENDING_TEXT)

    def test_names_page_before_names_are_entered(self):
        '''
        With more than one registration, the person paying is known on the
        page that asks who each registration is for, but the people that the
        registrations are for are not known yet.
        '''
        self.cart(self.first_time, self.series, self.other_series, checkout=True)
        response = self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Voucher', 'lastName': 'Customer',
            'email': 'test@customer.com', 'agreeToPolicies': True,
        }, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse('multiRegNameInfo'))

        self.assertTrue(response.context_data['voucher']['customerPending'])
        self.assertContains(response, PENDING_TEXT)

    def test_customer_voucher_pending_until_payer_is_known(self):
        ''' A voucher for a specific customer depends on who is paying. '''
        customer = Customer.objects.create(
            first_name='Voucher', last_name='Customer', email='test@customer.com'
        )
        CustomerVoucher.objects.create(customer=customer, voucher=self.plain)

        response = self.cart(self.plain, self.series)
        self.assertTrue(response.json()['voucher_preview']['customer_pending'])

        self.new_session()
        self.cart(self.plain, self.series, self.other_series, checkout=True)
        response = self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Voucher', 'lastName': 'Customer',
            'email': 'test@customer.com', 'agreeToPolicies': True,
        }, follow=True)

        # On the names page, the person paying is known.
        self.assertEqual(response.redirect_chain[-1][0], reverse('multiRegNameInfo'))
        self.assertFalse(response.context_data['voucher']['customerPending'])
        self.assertNotContains(response, PENDING_TEXT)
