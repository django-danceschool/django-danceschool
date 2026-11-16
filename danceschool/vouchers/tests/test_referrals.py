from unittest import mock
import uuid

from django.contrib.auth.models import User

from dynamic_preferences.registries import global_preferences_registry

from danceschool.core.constants import getConstant, updateConstant
from danceschool.core.models import Customer

from ..handlers import provideCustomerReferralCode
from ..helpers import ensureReferralVouchersExist, generateUniqueVoucherId
from ..models import (
    Voucher, VoucherCredit, VoucherReferralDiscount, VoucherReferralDiscountUse
)
from .base import BaseVouchersTest


class ReferralProgramTest(BaseVouchersTest):
    '''
    With the referral program, each customer has a voucher code to give to
    others (the referee voucher). A new customer who registers with that code
    gets $5 off, and the customer who referred them then gets a $7 credit on
    a voucher of their own (the referrer voucher), which is applied
    automatically the next time that they register.
    '''

    def setUp(self):
        self.gp = global_preferences_registry.manager()
        updateConstant('vouchers__enableVouchers', True)
        self.gp['referrals__enableReferralProgram'] = True
        self.gp['referrals__refereeDiscount'] = 5.0
        self.gp['referrals__referrerDiscount'] = 7.0

        # The customer who refers others has a user account, which is how
        # their referrer voucher is found when they register.
        self.referrer_user = User.objects.create_user(
            'referrer', 'referrer@customer.com', 'pass',
            first_name='Referring', last_name='Customer',
        )
        self.referrer = Customer.objects.create(
            first_name='Referring', last_name='Customer',
            email='referrer@customer.com', user=self.referrer_user,
        )
        self.series = self.create_series(
            classDescription=self.levelOneClassDescription
        )
        self.other_series = self.create_series(
            classDescription=self.levelTwoClassDescription
        )
        self.price = self.series.getBasePrice()

    def tearDown(self):
        self.gp['referrals__enableReferralProgram'] = False
        self.gp['referrals__refereeDiscount'] = 0.0
        self.gp['referrals__referrerDiscount'] = 0.0

    def test_referral_vouchers_are_created(self):
        referral = ensureReferralVouchersExist(self.referrer)

        self.assertIsInstance(referral, VoucherReferralDiscount)
        self.assertEqual(referral.referrerBonus, 7)

        # The voucher to give to others is for new customers, $5 at a time.
        referee_voucher = referral.referreeVoucher
        self.assertEqual(referee_voucher.maxAmountPerUse, 5)
        self.assertTrue(referee_voucher.forFirstTimeCustomersOnly)
        self.assertEqual(
            referee_voucher.category, getConstant('referrals__refereeCategory')
        )

        # The voucher that collects the referrer's credits starts out empty,
        # and it belongs to the referrer.
        referrer_voucher = referral.referrerVoucher
        self.assertEqual(referrer_voucher.amountLeft, 0)
        self.assertFalse(referrer_voucher.beforeTax)
        self.assertEqual(
            referrer_voucher.category, getConstant('referrals__referrerCategory')
        )
        self.assertEqual(self.referrer.getReferralVouchers(), [referrer_voucher])

    def test_referral_vouchers_are_only_created_once(self):
        first = ensureReferralVouchersExist(self.referrer)
        second = ensureReferralVouchersExist(self.referrer)

        self.assertEqual(first, second)
        self.assertEqual(VoucherReferralDiscount.objects.count(), 1)
        self.assertEqual(Voucher.objects.count(), 2)

    def test_referral_amounts_follow_the_site_settings(self):
        ''' A change to the amounts applies to existing referral vouchers. '''
        ensureReferralVouchersExist(self.referrer)
        self.gp['referrals__refereeDiscount'] = 6.0
        self.gp['referrals__referrerDiscount'] = 8.0

        referral = ensureReferralVouchersExist(self.referrer)
        referral.refresh_from_db()

        self.assertEqual(referral.referrerBonus, 8)
        self.assertEqual(referral.referreeVoucher.maxAmountPerUse, 6)

    def test_referral_code_is_provided_for_customer_profile(self):
        result = provideCustomerReferralCode(sender=None, customer=self.referrer)
        referral = VoucherReferralDiscount.objects.get()

        self.assertEqual(
            result, {'referralVoucherId': referral.referreeVoucher.voucherId}
        )

    def test_no_referral_code_when_program_is_disabled(self):
        self.gp['referrals__enableReferralProgram'] = False

        self.assertIsNone(
            provideCustomerReferralCode(sender=None, customer=self.referrer)
        )
        self.assertFalse(VoucherReferralDiscount.objects.exists())

    def test_referral_from_start_to_finish(self):
        referral = ensureReferralVouchersExist(self.referrer)
        code = referral.referreeVoucher.voucherId

        # A new customer registers with the code, and gets $5 off.
        response = self.checkout(
            self.series, code=code,
            name=('New', 'Customer'), email='new@customer.com',
        )
        self.assertVoucherApplied(response, referral.referreeVoucher, 5)
        self.assertEqual(self.get_invoice().outstandingBalance, self.price - 5)

        # The referrer is not credited until the new customer has paid.
        self.assertEqual(referral.referrerVoucher.amountLeft, 0)
        self.pay()
        self.assertEqual(referral.referrerVoucher.amountLeft, 7)
        self.assertEqual(VoucherCredit.objects.get().voucher, referral.referrerVoucher)
        self.assertEqual(
            VoucherReferralDiscountUse.objects.get().voucherReferralDiscount, referral
        )

        # The credit is applied automatically when the referrer registers.
        self.new_session()
        response = self.checkout(
            self.other_series,
            name=('Referring', 'Customer'), email='referrer@customer.com',
        )
        self.assertVoucherApplied(response, referral.referrerVoucher, 7)
        self.assertEqual(self.get_invoice().outstandingBalance, self.price - 7)

        self.pay()
        self.assertEqual(referral.referrerVoucher.amountLeft, 0)

    def test_referee_voucher_is_for_new_customers_only(self):
        referral = ensureReferralVouchersExist(self.referrer)
        code = referral.referreeVoucher.voucherId

        # Register without the code, to become an existing customer.
        self.checkout(
            self.series, name=('Existing', 'Customer'), email='existing@customer.com',
        )
        self.pay()

        self.new_session()
        response = self.checkout(
            self.other_series, code=code,
            name=('Existing', 'Customer'), email='existing@customer.com',
        )
        self.assertVoucherRefused(response)

    def test_unique_voucher_id_avoids_existing_ids(self):
        ''' A new voucher code is never the same as an existing one. '''
        taken = uuid.UUID('11111111-2222-3333-4444-555555555555')
        free = uuid.UUID('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
        self.create_voucher(voucherId='REF' + taken.hex[0:8].upper())

        with mock.patch('danceschool.vouchers.helpers.uuid.uuid4', side_effect=[taken, free]):
            result = generateUniqueVoucherId('REF')

        self.assertEqual(result, 'REF' + free.hex[0:8].upper())
