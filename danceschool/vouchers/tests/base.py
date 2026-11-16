import json

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
