import json

from django.urls import reverse

from danceschool.core.constants import updateConstant
from danceschool.core.models import Customer, PricingTier

from ..models import CustomerVoucher, Voucher
from .base import BaseVouchersTest


NEW = ('New', 'Customer', 'new@customer.com')
OLD = ('Old', 'Customer', 'old@customer.com')


class VoucherAttendeeTest(BaseVouchersTest):
    '''
    A voucher for first-time customers (or for previous customers) applies to
    the registrations of the people who meet that condition, and not to the
    other registrations on the same invoice. A voucher for a specific
    customer or customer group depends on who is paying, and it applies to
    the whole invoice. Series A is $20 and series B is $30.
    '''

    def setUp(self):
        updateConstant('vouchers__enableVouchers', True)
        self.s_a = self.create_series(
            pricingTier=PricingTier.objects.create(
                name='Tier A', onlinePrice=20, doorPrice=20, dropinPrice=20,
            ),
            classDescription=self.levelOneClassDescription,
        )
        self.s_b = self.create_series(
            pricingTier=PricingTier.objects.create(
                name='Tier B', onlinePrice=30, doorPrice=30, dropinPrice=30,
            ),
            classDescription=self.levelTwoClassDescription,
        )

        # The old customer has registered and paid before.
        s_earlier = self.create_series()
        self.checkout(s_earlier, name=OLD[:2], email=OLD[2])
        self.pay()
        self.old_customer = Customer.objects.get(email=OLD[2])
        self.assertGreater(self.old_customer.numEventRegistrations, 0)
        self.new_session()

    def register(self, payer, attendees, code=None, gift=None):
        '''
        The payer registers for series A for the first attendee, and series B
        for the second, with a voucher code passed with the cart (code) or
        entered on the customer information form (gift). Returns the final
        response.
        '''
        cart_data = {
            'items': [
                {
                    'item_type': 'Event', 'item_id': event.id,
                    'sku': 'EVENT_%s_GENERAL' % event.id, 'quantity': 1,
                } for event in [self.s_a, self.s_b]
            ],
            'checkout': True,
        }
        if code:
            cart_data['discount_code'] = code
        response = self.client.post(
            reverse('cart'), data=json.dumps(cart_data),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)

        post_data = {
            'firstName': payer[0], 'lastName': payer[1], 'email': payer[2],
            'agreeToPolicies': True,
        }
        if gift:
            post_data['gift'] = gift
        response = self.client.post(reverse('getStudentInfo'), post_data, follow=True)
        if not response.redirect_chain:
            return response
        self.assertEqual(response.redirect_chain[-1][0], reverse('multiRegNameInfo'))

        reg = self.get_invoice().registration
        name_post = {}
        for er in reg.eventregistration_set.all():
            attendee = attendees[0] if er.event == self.s_a else attendees[1]
            name_post['er_%s_firstName' % er.id] = attendee[0]
            name_post['er_%s_lastName' % er.id] = attendee[1]
            name_post['er_%s_email' % er.id] = attendee[2]
        response = self.client.post(reverse('multiRegNameInfo'), name_post, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse('showRegSummary'))
        return response

    def totals(self):
        ''' The totals for series A and B, and the amount of the voucher used. '''
        invoice = self.get_invoice()
        reg = invoice.registration
        items = list(invoice.invoiceitem_set.all())
        self.assertAlmostEqual(
            invoice.total, sum([x.total for x in items]), places=4,
            msg='Invoice total does not match its items'
        )
        return (
            reg.eventregistration_set.get(event=self.s_a).invoiceItem.total,
            reg.eventregistration_set.get(event=self.s_b).invoiceItem.total,
            sum([x.amount for x in invoice.voucheruse_set.all()]),
        )

    def first_time_voucher(self):
        return Voucher.objects.create(
            voucherId='NEWBIE', name='New Customer Voucher', originalAmount=100,
            forFirstTimeCustomersOnly=True,
        )

    def previous_customer_voucher(self):
        return Voucher.objects.create(
            voucherId='WELCOME_BACK', name='Previous Customer Voucher',
            originalAmount=100, forPreviousCustomersOnly=True,
        )

    # -- Vouchers for first-time customers --------------------------------------

    def test_first_time_voucher_covers_only_new_customer(self):
        ''' The new customer pays for themselves and an old customer. '''
        voucher = self.first_time_voucher()
        for argument in ['code', 'gift']:
            self.new_session()
            self.register(NEW, [NEW, OLD], **{argument: voucher.voucherId})
            a, b, used = self.totals()
            self.assertAlmostEqual(a, 0, places=2, msg=argument)
            self.assertAlmostEqual(b, 30, places=2, msg=argument)
            self.assertAlmostEqual(used, 20, places=2, msg=argument)

    def test_first_time_voucher_for_new_friend_of_old_customer(self):
        ''' The old customer pays for themselves and a new customer. '''
        voucher = self.first_time_voucher()
        for argument in ['code', 'gift']:
            self.new_session()
            self.register(OLD, [OLD, NEW], **{argument: voucher.voucherId})
            a, b, used = self.totals()
            self.assertAlmostEqual(a, 20, places=2, msg=argument)
            self.assertAlmostEqual(b, 0, places=2, msg=argument)
            self.assertAlmostEqual(used, 30, places=2, msg=argument)

    def test_first_time_voucher_with_no_new_customer(self):
        voucher = self.first_time_voucher()
        other_old = ('Other', 'Customer', 'other@customer.com')
        self.checkout(self.create_series(), name=other_old[:2], email=other_old[2])
        self.pay()

        self.new_session()
        self.register(OLD, [OLD, other_old], code=voucher.voucherId)
        a, b, used = self.totals()
        self.assertEqual((a, b, used), (20, 30, 0))

    def test_first_time_voucher_for_entire_invoice(self):
        ''' Once one registration qualifies, the voucher covers everything. '''
        voucher = self.first_time_voucher()
        voucher.appliesToEntireInvoice = True
        voucher.save()

        self.register(NEW, [NEW, OLD], code=voucher.voucherId)
        a, b, used = self.totals()
        self.assertEqual((a, b), (0, 0))
        self.assertAlmostEqual(used, 50, places=2)

    def test_first_time_voucher_after_changing_customer_information(self):
        '''
        With one registration (so no names are asked for separately), the
        person entering the customer information is the person it is for,
        even if another person was entered on an earlier attempt.
        '''
        voucher = self.first_time_voucher()
        cart_data = {
            'items': [{
                'item_type': 'Event', 'item_id': self.s_a.id,
                'sku': 'EVENT_%s_GENERAL' % self.s_a.id, 'quantity': 1,
            }],
            'checkout': True,
        }
        self.client.post(
            reverse('cart'), data=json.dumps(cart_data), content_type='application/json',
        )

        def submit(person, **extra):
            data = {
                'firstName': person[0], 'lastName': person[1], 'email': person[2],
                'agreeToPolicies': True,
            }
            data.update(extra)
            return self.client.post(reverse('getStudentInfo'), data, follow=True)

        # The old customer cannot use the voucher.
        response = submit(OLD, gift=voucher.voucherId)
        self.assertFalse(response.redirect_chain)
        self.assertTrue(response.context_data['form'].errors.get('gift'))

        # The old customer goes on without it, and then goes back and enters
        # the information of a new customer, with the voucher.
        submit(OLD)
        self.assertEqual(
            self.get_invoice().registration.eventregistration_set.get().customer,
            self.old_customer
        )
        response = submit(NEW, gift=voucher.voucherId)

        self.assertVoucherApplied(response, voucher, 20)

    def test_eligible_items_before_names_are_known(self):
        '''
        Before it is known who a registration is for, it counts as a
        registration for a first-time customer, and not for a previous one.
        '''
        self.client.post(
            reverse('cart'), content_type='application/json',
            data=json.dumps({
                'items': [{
                    'item_type': 'Event', 'item_id': self.s_a.id,
                    'sku': 'EVENT_%s_GENERAL' % self.s_a.id, 'quantity': 1,
                }],
                'checkout': True,
            }),
        )
        items = self.get_invoice().invoiceitem_set.all()
        self.assertIsNone(items.get().eventRegistration.customer)

        self.assertEqual(
            self.first_time_voucher().eligibleItemIds(items), {str(items.get().id)}
        )
        self.assertEqual(self.previous_customer_voucher().eligibleItemIds(items), set())

    # -- Vouchers for previous customers ----------------------------------------

    def test_previous_customer_voucher_covers_only_old_customer(self):
        voucher = self.previous_customer_voucher()
        for argument in ['code', 'gift']:
            self.new_session()
            self.register(NEW, [NEW, OLD], **{argument: voucher.voucherId})
            a, b, used = self.totals()
            self.assertAlmostEqual(a, 20, places=2, msg=argument)
            self.assertAlmostEqual(b, 0, places=2, msg=argument)
            self.assertAlmostEqual(used, 30, places=2, msg=argument)

    # -- Vouchers for a specific customer ---------------------------------------

    def test_customer_voucher_covers_whole_invoice_of_that_customer(self):
        '''
        A voucher for a specific customer (such as a referral credit) can be
        used for everything that the customer pays for, including another
        person's registration.
        '''
        voucher = Voucher.objects.create(
            voucherId='OLD_CREDIT', name='Credit for Old Customer', originalAmount=100,
        )
        CustomerVoucher.objects.create(customer=self.old_customer, voucher=voucher)

        self.register(OLD, [OLD, NEW], code=voucher.voucherId)
        a, b, used = self.totals()
        self.assertEqual((a, b), (0, 0))
        self.assertAlmostEqual(used, 50, places=2)

        # Someone else cannot use it, even for the old customer's registration.
        self.new_session()
        self.register(NEW, [NEW, OLD], code=voucher.voucherId)
        a, b, used = self.totals()
        self.assertEqual((a, b, used), (20, 30, 0))
