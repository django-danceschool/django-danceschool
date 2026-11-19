import json

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from dynamic_preferences.registries import global_preferences_registry

from danceschool.core.constants import updateConstant
from danceschool.core.models import (
    EventAddOn, Invoice, PricingTier, Series, TaxJurisdiction, TaxRule
)

from ..models import ClassVoucher, Voucher
from .base import BaseVouchersTest


class VoucherEligibilityTest(BaseVouchersTest):
    '''
    A voucher that is restricted to specific classes (or levels, categories
    or sessions) applies only to the items on an invoice that qualify for it,
    unless it is allowed to be used for anything on the invoice. Series A
    ($20) qualifies for the voucher, and series B ($30) does not.
    '''

    def setUp(self):
        self.gp = global_preferences_registry.manager()
        updateConstant('vouchers__enableVouchers', True)
        self.tier_a = PricingTier.objects.create(
            name='Tier A', onlinePrice=20, doorPrice=20, dropinPrice=20,
        )
        self.tier_b = PricingTier.objects.create(
            name='Tier B', onlinePrice=30, doorPrice=30, dropinPrice=30,
        )
        self.s_a = self.create_series(
            pricingTier=self.tier_a, classDescription=self.levelOneClassDescription
        )
        self.s_b = self.create_series(
            pricingTier=self.tier_b, classDescription=self.levelTwoClassDescription
        )
        self.voucher = self.restricted_voucher(50)

    def restricted_voucher(self, amount, voucherId='CLASS_A_ONLY', **kwargs):
        voucher = Voucher.objects.create(
            voucherId=voucherId, name='Class A Voucher', originalAmount=amount,
            **kwargs
        )
        ClassVoucher.objects.create(
            classDescription=self.levelOneClassDescription, voucher=voucher
        )
        return voucher

    def item_totals(self, event):
        reg = self.get_invoice().registration
        return [
            er.invoiceItem.total for er in
            reg.eventregistration_set.filter(event=event).order_by('id')
        ]

    def assertInvoiceMatchesItems(self):
        '''
        The totals of the invoice are the sums of the totals of its items, so
        no allocation was lost.
        '''
        invoice = self.get_invoice()
        items = list(invoice.invoiceitem_set.all())
        for field in ['total', 'taxes', 'adjustments']:
            self.assertAlmostEqual(
                getattr(invoice, field), sum([getattr(x, field) for x in items]),
                places=4, msg='Invoice %s does not match its items' % field
            )

    def voucher_amount(self, voucher):
        use = self.get_invoice().voucheruse_set.filter(voucher=voucher).first()
        return use.amount if use else 0

    # -- Which items are eligible -----------------------------------------------

    def test_voucher_covers_only_qualifying_class(self):
        '''
        A $50 voucher for series A, with both series in the cart, covers all
        of series A ($20), and none of series B.
        '''
        response = self.checkout(self.s_a, self.s_b, code=self.voucher.voucherId)

        self.assertVoucherApplied(response, self.voucher, 20)
        self.assertAlmostEqual(self.item_totals(self.s_a)[0], 0, places=2)
        self.assertAlmostEqual(self.item_totals(self.s_b)[0], 30, places=2)
        self.assertAlmostEqual(self.get_invoice().total, 30, places=2)
        self.assertInvoiceMatchesItems()

    def test_voucher_for_entire_invoice(self):
        '''
        A voucher that may be used for anything on the invoice covers both
        series, once series A qualifies it to be used.
        '''
        self.voucher.appliesToEntireInvoice = True
        self.voucher.save()

        response = self.checkout(self.s_a, self.s_b, code=self.voucher.voucherId)

        self.assertVoucherApplied(response, self.voucher, 50)
        self.assertAlmostEqual(self.get_invoice().total, 0, places=2)
        self.assertInvoiceMatchesItems()

    def test_voucher_for_entire_invoice_still_needs_qualifying_class(self):
        self.voucher.appliesToEntireInvoice = True
        self.voucher.save()

        self.assertVoucherRefused(self.checkout(self.s_b, code=self.voucher.voucherId))

    def test_qualifying_class_after_drop_ins_by_others(self):
        '''
        A class that someone else has dropped in to still qualifies for the
        voucher when another customer registers for it in full.
        '''
        self.s_a.allowDropins = True
        self.s_a.save()
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse('cart'), content_type='application/json',
            data=json.dumps({
                'items': [{
                    'item_type': 'Event', 'item_id': self.s_a.id,
                    'sku': 'EVENT_%s_GENERAL' % self.s_a.id, 'quantity': 1,
                    'dropIn': True,
                }],
                'checkout': True, 'payAtDoor': True,
            }),
        )
        self.assertEqual(response.status_code, 302)
        self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Drop', 'lastName': 'In', 'email': 'dropin@customer.com',
            'agreeToPolicies': True,
        })
        self.pay()

        self.new_session()
        response = self.checkout(self.s_a, code=self.voucher.voucherId)

        self.assertVoucherApplied(response, self.voucher, 20)

    def test_voucher_covers_pass_and_included_events(self):
        '''
        A pass that qualifies for the voucher includes series B, which is
        covered by the voucher as part of the pass.
        '''
        tier_pass = PricingTier.objects.create(
            name='Pass Tier', onlinePrice=40, doorPrice=40, dropinPrice=40,
        )
        s_pass = self.create_series(
            pricingTier=tier_pass, classDescription=self.levelOneClassDescription
        )
        EventAddOn.objects.create(
            event=s_pass, addOnEvent=self.s_b, order=0,
            allocationType=EventAddOn.AllocationType.fixed, allocationAmount=10,
        )

        response = self.checkout(s_pass, code=self.voucher.voucherId)

        self.assertVoucherApplied(response, self.voucher, 40)
        self.assertAlmostEqual(self.get_invoice().total, 0, places=2)
        self.assertInvoiceMatchesItems()

    def test_voucher_for_included_event_not_usable_for_pass(self):
        '''
        A voucher for a class that is included with a pass cannot be used
        when only the pass is being registered for, because the included
        class qualifies only if the pass does.
        '''
        tier_pass = PricingTier.objects.create(
            name='Pass Tier', onlinePrice=40, doorPrice=40, dropinPrice=40,
        )
        s_pass = self.create_series(
            pricingTier=tier_pass, classDescription=self.levelTwoClassDescription
        )
        EventAddOn.objects.create(
            event=s_pass, addOnEvent=self.s_a, order=0,
            allocationType=EventAddOn.AllocationType.fixed, allocationAmount=10,
        )

        # Entered on the customer information form, the code is an error.
        response = self.checkout(s_pass, gift=self.voucher.voucherId)
        self.assertFalse(response.redirect_chain)
        self.assertTrue(response.context_data['form'].errors.get('gift'))

        # Passed with the cart, the voucher is not applied to the invoice.
        # (The price of a pass is not its gross total, which includes the
        # prices of the included events on their own, so this does not use
        # assertVoucherRefused().)
        self.new_session()
        response = self.checkout(s_pass, code=self.voucher.voucherId)
        self.assertEqual(response.redirect_chain[-1][0], reverse('showRegSummary'))
        self.assertFalse(
            self.get_invoice().voucheruse_set.filter(voucher=self.voucher).exists()
        )
        self.assertAlmostEqual(self.get_invoice().total, 40, places=2)

    def test_voucher_for_drop_in_to_qualifying_class(self):
        ''' A drop-in to a qualifying class is a registration for that class. '''
        self.s_a.allowDropins = True
        self.s_a.save()
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse('cart'), content_type='application/json',
            data=json.dumps({
                'items': [{
                    'item_type': 'Event', 'item_id': self.s_a.id,
                    'sku': 'EVENT_%s_GENERAL' % self.s_a.id, 'quantity': 1,
                    'dropIn': True,
                }],
                'checkout': True, 'payAtDoor': True,
                'discount_code': self.voucher.voucherId,
            }),
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Drop', 'lastName': 'In', 'email': 'dropin@customer.com',
            'agreeToPolicies': True,
        }, follow=True)

        self.assertVoucherApplied(response, self.voucher, 20)

    # -- More than one voucher, and tax -----------------------------------------

    def test_restricted_voucher_and_gift_certificate_with_two_tax_rates(self):
        '''
        Series A is taxed at 10% and series B at 5%. A $10 voucher for series
        A comes off before tax, so A is $10 plus $1 tax, and B is $30 plus
        $1.50 tax. A gift certificate then pays the remaining $42.50.
        '''
        jurisdiction = TaxJurisdiction.objects.create(name='Two Rates', defaultRate=5)
        TaxRule.objects.create(
            jurisdiction=jurisdiction,
            itemType=ContentType.objects.get_for_model(Series), rate=10,
        )
        self.s_b.taxRateOverride = 5
        self.s_b.save()
        self.defaultLocation.taxJurisdiction = jurisdiction
        self.defaultLocation.save()
        self.gp['registration__buyerPaysSalesTax'] = True

        voucher = self.restricted_voucher(10, voucherId='CLASS_A_TEN')
        gift = Voucher.objects.create(
            voucherId='GIFT', name='Gift Certificate', originalAmount=100,
            beforeTax=False,
        )

        self.checkout(self.s_a, self.s_b, code=voucher.voucherId)
        invoice = self.get_invoice()
        from ..models import VoucherUse
        VoucherUse.objects.create(
            voucher=gift, invoice=invoice, amount=0, beforeTax=False,
        )
        self.client.get(reverse('showRegSummary'))
        invoice = self.get_invoice()

        self.assertAlmostEqual(self.voucher_amount(voucher), 10, places=4)
        self.assertAlmostEqual(self.item_totals(self.s_a)[0], 10, places=4)
        self.assertAlmostEqual(self.item_totals(self.s_b)[0], 30, places=4)
        self.assertAlmostEqual(invoice.taxes, 2.5, places=4)
        self.assertAlmostEqual(self.voucher_amount(gift), 42.5, places=4)
        self.assertAlmostEqual(invoice.outstandingBalance, 0, places=4)
        self.assertInvoiceMatchesItems()

    def test_summary_page_reload_gives_same_totals(self):
        self.checkout(self.s_a, self.s_b, code=self.voucher.voucherId)
        self.client.get(reverse('showRegSummary'))

        self.assertAlmostEqual(self.voucher_amount(self.voucher), 20, places=2)
        self.assertAlmostEqual(self.item_totals(self.s_a)[0], 0, places=2)
        self.assertAlmostEqual(self.item_totals(self.s_b)[0], 30, places=2)
        self.assertInvoiceMatchesItems()

    # -- Previews ---------------------------------------------------------------

    def cart_items(self, *events):
        return [
            {
                'item_type': 'Event', 'item_id': event.id,
                'sku': 'EVENT_%s_GENERAL' % event.id, 'quantity': 1,
            } for event in events
        ]

    def test_cart_preview_shows_amount_for_qualifying_class(self):
        response = self.client.post(
            reverse('cart'), content_type='application/json',
            data=json.dumps({
                'items': self.cart_items(self.s_a, self.s_b),
                'discount_code': self.voucher.voucherId,
            }),
        )
        preview = response.json().get('voucher_preview')
        self.assertAlmostEqual(preview['voucher_amount'], 20, places=2)

        response = self.client.get(reverse('cartSummary'))
        preview = response.context_data['voucher_preview']
        self.assertAlmostEqual(preview['voucher_amount'], 20, places=2)

    def _preview_and_summary(self, voucher):
        '''
        Return the amount of the voucher that is shown on the customer
        information page, and the amount that is used on the summary page.
        '''
        response = self.client.post(
            reverse('cart'), content_type='application/json',
            data=json.dumps({
                'items': self.cart_items(self.s_a, self.s_b), 'checkout': True,
                'discount_code': voucher.voucherId,
            }),
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.get(reverse('getStudentInfo'))
        preview = response.context_data['voucher']['voucherAmount']

        response = self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Voucher', 'lastName': 'Customer',
            'email': 'test@customer.com', 'agreeToPolicies': True,
        }, follow=True)

        # With two registrations, the name for each one is asked for.
        if response.redirect_chain[-1][0] == reverse('multiRegNameInfo'):
            name_post = {}
            for er in self.get_invoice().registration.eventregistration_set.all():
                name_post['er_%s_firstName' % er.id] = 'Voucher'
                name_post['er_%s_lastName' % er.id] = 'Customer'
                name_post['er_%s_email' % er.id] = 'test@customer.com'
            response = self.client.post(
                reverse('multiRegNameInfo'), name_post, follow=True
            )
        self.assertEqual(response.redirect_chain[-1][0], reverse('showRegSummary'))
        return preview, self.voucher_amount(voucher)

    def test_customer_information_preview_matches_summary(self):
        preview, used = self._preview_and_summary(self.voucher)
        self.assertAlmostEqual(preview, 20, places=2)
        self.assertAlmostEqual(used, 20, places=2)

    def test_after_tax_voucher_preview_matches_summary(self):
        '''
        A voucher applied after tax is limited to the price of the qualifying
        class plus its 10% tax.
        '''
        jurisdiction = TaxJurisdiction.objects.create(name='Ten Percent', defaultRate=10)
        self.defaultLocation.taxJurisdiction = jurisdiction
        self.defaultLocation.save()
        self.gp['registration__buyerPaysSalesTax'] = True
        voucher = self.restricted_voucher(
            50, voucherId='CLASS_A_AFTER_TAX', beforeTax=False
        )

        preview, used = self._preview_and_summary(voucher)

        self.assertAlmostEqual(preview, 22, places=2)
        self.assertAlmostEqual(used, 22, places=2)
        self.assertAlmostEqual(self.get_invoice().outstandingBalance, 33, places=2)
        self.assertInvoiceMatchesItems()

    def test_admin_form_shows_option(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:vouchers_voucher_add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'appliesToEntireInvoice')
        response = self.client.get(
            reverse('admin:vouchers_voucher_change', args=[self.voucher.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'appliesToEntireInvoice')
