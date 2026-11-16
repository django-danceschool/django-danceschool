from django.urls import reverse

from ..models import DiscountCombo
from .base import DiscountAllocationBase


class DiscountAdminTest(DiscountAllocationBase):

    def setUp(self):
        super().setUp()
        self.combo = self.make_combo(percentDiscount=50)
        self.combo.voucherId = 'ADMINTEST'
        self.combo.studentsOnly = True
        self.combo.firstXRegistered = 3
        self.combo.save()
        self.client.force_login(self.superuser)
        self.url = reverse('admin:discounts_discountcombo_changelist')

    def test_changelist_describes_restrictions(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.combo.name)
        self.assertContains(response, 'Voucher code ADMINTEST required')
        self.assertContains(response, 'Students only')
        self.assertContains(response, 'First 3 to register')

    def test_disable_and_enable_actions(self):
        response = self.client.post(self.url, {
            'action': 'disableDiscount', '_selected_action': [self.combo.pk],
        }, follow=True)
        self.assertContains(response, '1 discount was successfully disabled.')
        self.assertFalse(DiscountCombo.objects.get(pk=self.combo.pk).active)

        response = self.client.post(self.url, {
            'action': 'enableDiscount', '_selected_action': [self.combo.pk],
        }, follow=True)
        self.assertContains(response, '1 discount was successfully enabled.')
        self.assertTrue(DiscountCombo.objects.get(pk=self.combo.pk).active)


class DiscountStatsTest(DiscountAllocationBase):
    '''
    The statistics on the use of discounts only count discounts on
    registrations that have been finalized.
    '''

    def setUp(self):
        super().setUp()
        self.combo = self.make_combo(percentDiscount=50)
        self.s_a = self.create_series(pricingTier=self.tier_a)
        self.s_b = self.create_series(pricingTier=self.tier_b)

    def get_json(self, url_name):
        self.new_session()
        self.client.force_login(self.superuser)
        response = self.client.get(reverse(url_name))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_stats_require_staff(self):
        for url_name in ['popularDiscountsJSON', 'discountFrequencyJSON']:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 302)

    def test_unpaid_registration_is_not_counted(self):
        self.checkout(self.s_b)

        self.assertEqual(self.get_json('popularDiscountsJSON'), [])
        self.assertEqual(self.get_json('discountFrequencyJSON'), [])

    def test_paid_registrations_are_counted(self):
        # One registration with a discount, and one without.
        self.pay(self.checkout(self.s_b, names=[('First', 'Person')]))
        self.new_session()
        self.pay(self.checkout(self.s_a, names=[('Second', 'Person')]))

        self.assertEqual(
            self.get_json('popularDiscountsJSON'),
            [{'name': self.combo.name, 'counter': 1}]
        )
        self.assertEqual(
            self.get_json('discountFrequencyJSON'),
            [{'discounts': 0, 'count': 1}, {'discounts': 1, 'count': 1}]
        )
