from unittest import mock, skipUnless
import uuid

from django.apps import apps
from django.urls import reverse

from ..helpers import generateUniqueVoucherId
from ..models import Voucher, VoucherCategory
from .base import BaseVouchersTest


@skipUnless(
    apps.is_installed('danceschool.discounts'), 'The discounts app is not installed.'
)
class GeneratedCodeTest(BaseVouchersTest):
    '''
    A generated voucher code is never the code of a discount, because a
    voucher with the same code as a discount could never be used.
    '''

    def create_discount(self, code):
        from danceschool.discounts.models import DiscountCategory, DiscountCombo
        return DiscountCombo.objects.create(
            name='Discount', category=DiscountCategory.objects.get(id=1),
            voucherId=code, discountType=DiscountCombo.DiscountType.dollarDiscount,
            dollarDiscount=10,
        )

    def test_code_in_use(self):
        self.create_voucher(voucherId='VOUCHERCODE')
        self.create_discount('DISCOUNTCODE')

        self.assertTrue(Voucher.codeInUse('VOUCHERCODE'))
        self.assertTrue(Voucher.codeInUse('DISCOUNTCODE'))
        self.assertFalse(Voucher.codeInUse('OTHERCODE'))

    def test_referral_code_avoids_discount_codes(self):
        taken = uuid.UUID('11111111-2222-3333-4444-555555555555')
        free = uuid.UUID('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
        self.create_discount('REF' + taken.hex[0:8].upper())

        with mock.patch('danceschool.vouchers.helpers.uuid.uuid4', side_effect=[taken, free]):
            result = generateUniqueVoucherId('REF')

        self.assertEqual(result, 'REF' + free.hex[0:8].upper())

    def test_gift_certificate_code_avoids_discount_codes(self):
        self.create_discount('GC_AAAAAAAAAA')

        with mock.patch(
            'danceschool.vouchers.models.random.choice', side_effect=['A'] * 10 + ['B'] * 10
        ):
            voucher = Voucher.create_new_code(
                prefix='GC_', name='Gift certificate', originalAmount=10
            )

        self.assertEqual(voucher.voucherId, 'GC_BBBBBBBBBB')

    def test_generation_page_avoids_discount_codes(self):
        self.create_discount('PROMO_AAAAAAAAAA')
        self.client.force_login(self.superuser)

        with mock.patch(
            'danceschool.vouchers.views.random.choice', side_effect=['A'] * 10 + ['B'] * 10
        ):
            response = self.client.get(reverse('generateVoucher') + '?prefix=PROMO_')
        self.assertEqual(
            response.context_data['form'].initial['voucherId'], 'PROMO_BBBBBBBBBB'
        )

        # The code is checked again when the form is submitted, since it can
        # be changed.
        category = VoucherCategory.objects.create(name='Promotions')
        response = self.client.post(reverse('generateVoucher'), {
            'voucherId': 'PROMO_AAAAAAAAAA', 'description': 'Promotion',
            'amount': 15, 'category': category.id,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context_data['form'].errors.get('voucherId'))
        self.assertFalse(Voucher.objects.exists())
