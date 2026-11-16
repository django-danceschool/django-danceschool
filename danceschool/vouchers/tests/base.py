import json

from django.test import Client
from django.urls import reverse

from danceschool.core.constants import REG_VALIDATION_STR
from danceschool.core.models import Registration, Invoice
from danceschool.core.tests.defaults import DefaultSchoolTestCase

from ..models import Voucher


class BaseVouchersTest(DefaultSchoolTestCase):
    '''
    Helper methods for tests of vouchers. This class has no tests of its own,
    so that test classes can inherit from it without repeating any tests.
    '''

    def create_voucher(self, **kwargs):

        v = Voucher(
            voucherId=kwargs.get('voucherId', 'TEST_VOUCHER'),
            name=kwargs.get('name', 'Test Voucher'),
            originalAmount=kwargs.get('originalAmount', 10),
            maxAmountPerUse=kwargs.get('maxAmountPerUse', None),
            disabled=kwargs.get('disabled', False),
            expirationDate=kwargs.get('expirationDate', None),
            forPreviousCustomersOnly=kwargs.get('forPreviousCustomersOnly', False),
            forFirstTimeCustomersOnly=kwargs.get('forFirstTimeCustomersOnly', False)
        )
        v.save()
        return v

    def register_to_check_voucher(self, voucherCode, series):
        '''
        This method makes it easy to determine whether vouchers are working
        correctly for a single class registration
        '''
        s = series

        sku = 'EVENT_{}_GENERAL'.format(s.id)
        response = self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{'item_type': 'Event', 'item_id': s.id, 'sku': sku, 'quantity': 1}],
                'checkout': True,
            }),
            content_type='application/json',
            follow=True,
        )
        self.assertEqual(response.redirect_chain, [(reverse('getStudentInfo'), 302)])

        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR].get('invoice_id')
        )
        tr = Registration.objects.filter(invoice=invoice).first()
        self.assertTrue(tr.eventregistration_set.filter(event__id=s.id).exists())
        self.assertFalse(tr.final)
        self.assertEqual(tr.payAtDoor, False)

        # Check that the student info page lists the correct item amounts and subtotal
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(response.context_data.get('invoice').total, s.getBasePrice())

        # Continue to the summary page
        post_data = {
            'firstName': 'Voucher',
            'lastName': 'Customer',
            'email': 'test@customer.com',
            'agreeToPolicies': True,
            'gift': voucherCode,
        }
        return self.client.post(reverse('getStudentInfo'), post_data, follow=True)

    def checkout(self, *events, **kwargs):
        '''
        Put one registration for each passed event in the cart, and proceed
        to the summary page (or to the customer information form, if it has
        errors). Returns the final response. A voucher code can be passed in
        one of the two ways that the site accepts it:

        - code: as the discount code of the cart
        - gift: in the voucher code field of the customer information form
        '''
        name = kwargs.get('name', ('Voucher', 'Customer'))
        email = kwargs.get('email', 'test@customer.com')

        cart_data = {
            'items': [
                {
                    'item_type': 'Event', 'item_id': event.id,
                    'sku': 'EVENT_{}_GENERAL'.format(event.id), 'quantity': 1,
                } for event in events
            ],
            'checkout': True,
        }
        if kwargs.get('code'):
            cart_data['discount_code'] = kwargs['code']
        if kwargs.get('payAtDoor'):
            cart_data['payAtDoor'] = True
            self.client.force_login(self.superuser)

        response = self.client.post(
            reverse('cart'), data=json.dumps(cart_data),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)

        post_data = {
            'firstName': name[0], 'lastName': name[1], 'email': email,
            'agreeToPolicies': True,
        }
        if kwargs.get('gift'):
            post_data['gift'] = kwargs['gift']
        response = self.client.post(reverse('getStudentInfo'), post_data, follow=True)

        # More than one registration means that the name of the person
        # associated with each registration is requested.
        if (
            response.redirect_chain and
            response.redirect_chain[-1][0] == reverse('multiRegNameInfo')
        ):
            reg = Registration.objects.get(invoice=self.get_invoice())
            name_post = {}
            for er in reg.eventregistration_set.all():
                name_post['er_%s_firstName' % er.id] = name[0]
                name_post['er_%s_lastName' % er.id] = name[1]
                name_post['er_%s_email' % er.id] = email
            response = self.client.post(
                reverse('multiRegNameInfo'), name_post, follow=True,
            )
        return response

    def get_invoice(self):
        ''' The current invoice for this session, as saved in the database. '''
        return Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR].get('invoice_id')
        )

    def pay(self):
        '''
        Pay the outstanding balance of the current invoice, which finalizes
        the registration and any use of vouchers. Returns the invoice.
        '''
        invoice = self.get_invoice()
        invoice.processPayment(
            amount=invoice.outstandingBalance, fees=0, paidOnline=False,
            methodName='Cash',
        )
        return Invoice.objects.get(id=invoice.id)

    def new_session(self):
        ''' Start over with an empty session, as a new visitor to the site. '''
        self.client = Client()

    def assertVoucherApplied(self, response, voucher, amount):
        ''' The summary page was reached, and the voucher was used. '''
        self.assertTrue(response.redirect_chain)
        self.assertEqual(response.redirect_chain[-1][0], reverse('showRegSummary'))
        uses = self.get_invoice().voucheruse_set.filter(voucher=voucher)
        self.assertEqual(uses.count(), 1)
        self.assertAlmostEqual(uses.first().amount, amount, places=2)

    def assertVoucherRefused(self, response):
        '''
        The voucher was not used. Either the customer information form
        reported an error for the voucher code, or the summary page was
        reached with nothing taken off of the price.
        '''
        if not response.redirect_chain:
            self.assertTrue(response.context_data['form'].errors.get('gift'))
            return
        invoice = self.get_invoice()
        self.assertEqual(
            [x.amount for x in invoice.voucheruse_set.all() if x.amount > 0], []
        )
        self.assertAlmostEqual(invoice.total, invoice.grossTotal, places=2)
        self.assertAlmostEqual(invoice.adjustments, 0, places=2)
