from django.utils import timezone

from datetime import timedelta

from danceschool.core.constants import updateConstant
from danceschool.core.models import (
    Customer, CustomerGroup, Event, EventOccurrence, EventSession,
    PublicEvent, PublicEventCategory, SeriesCategory
)

from ..models import (
    ClassVoucher, CustomerGroupVoucher, CustomerVoucher, DanceTypeVoucher,
    PublicEventCategoryVoucher, SeriesCategoryVoucher, SessionVoucher
)
from .base import BaseVouchersTest


class VoucherRestrictionsBase(BaseVouchersTest):
    '''
    Set up for tests of the restrictions on who can use a voucher, and what
    it can be used for. This class has no tests of its own.

    A voucher code reaches the site in one of two ways: in the voucher code
    field of the customer information form, or as the discount code of the
    cart. The subclasses of this class run the same tests each way, by
    setting the name of the argument to checkout() that is used.
    '''

    code_argument = None

    def setUp(self):
        updateConstant('vouchers__enableVouchers', True)
        self.voucher = self.create_voucher(originalAmount=10)
        self.series = self.create_series(
            classDescription=self.levelOneClassDescription
        )
        self.other_series = self.create_series(
            classDescription=self.levelTwoClassDescription
        )

    def use_voucher(self, *events, **kwargs):
        kwargs[self.code_argument] = self.voucher.voucherId
        return self.checkout(*events, **kwargs)

    def create_public_event(self, title, category=None):
        start = timezone.now() + timedelta(days=1)
        event = PublicEvent(
            title=title, slug=title.lower().replace(' ', '-'),
            pricingTier=self.defaultPricing, location=self.defaultLocation,
            status=Event.RegStatus.enabled, category=category,
        )
        event.save()
        EventOccurrence.objects.create(
            event=event, startTime=start, endTime=start + timedelta(hours=1),
        )
        event.save()
        return event

    def assertUsableOnlyFor(self, usable, not_usable):
        ''' The voucher can be used for one event, but not for another. '''
        self.assertVoucherApplied(self.use_voucher(usable), self.voucher, 10)
        self.new_session()
        self.assertVoucherRefused(self.use_voucher(not_usable))


class VoucherRestrictionTests(object):
    '''
    The tests of voucher restrictions, which are run by the two classes at
    the end of this file.
    '''

    # -- How and when the voucher is used --------------------------------------

    def test_unrestricted_voucher(self):
        self.assertVoucherApplied(self.use_voucher(self.series), self.voucher, 10)

    def test_voucher_with_nothing_left(self):
        self.voucher.refundAmount = 10
        self.voucher.save()
        self.assertVoucherRefused(self.use_voucher(self.series))

    def test_single_use_voucher_cannot_be_used_twice(self):
        self.voucher.singleUse = True
        self.voucher.maxAmountPerUse = 5
        self.voucher.save()

        self.assertVoucherApplied(self.use_voucher(self.series), self.voucher, 5)
        self.pay()

        self.new_session()
        self.assertVoucherRefused(self.use_voucher(self.other_series))

    def test_door_only_voucher(self):
        self.voucher.doorOnly = True
        self.voucher.save()

        self.assertVoucherRefused(self.use_voucher(self.series))
        self.new_session()
        self.assertVoucherApplied(
            self.use_voucher(self.series, payAtDoor=True), self.voucher, 10
        )

    # -- Who uses the voucher --------------------------------------------------

    def test_voucher_for_first_time_customers(self):
        self.voucher.forFirstTimeCustomersOnly = True
        self.voucher.maxAmountPerUse = 5
        self.voucher.save()

        self.assertVoucherApplied(self.use_voucher(self.series), self.voucher, 5)
        self.pay()

        # The same customer is no longer a first time customer.
        self.new_session()
        self.assertVoucherRefused(self.use_voucher(self.other_series))

    def test_voucher_for_previous_customers(self):
        self.voucher.forPreviousCustomersOnly = True
        self.voucher.save()

        self.assertVoucherRefused(self.use_voucher(self.series))

        # Register without the voucher, to become a previous customer.
        self.new_session()
        self.checkout(self.series)
        self.pay()

        self.new_session()
        self.assertVoucherApplied(self.use_voucher(self.other_series), self.voucher, 10)

    def _customer_restriction(self, restrict):
        customer = Customer.objects.create(
            first_name='Special', last_name='Customer', email='special@customer.com'
        )
        restrict(customer)

        self.assertVoucherRefused(self.use_voucher(self.series))
        self.new_session()
        self.assertVoucherApplied(
            self.use_voucher(
                self.series, name=('Special', 'Customer'), email='special@customer.com'
            ),
            self.voucher, 10
        )

    def test_voucher_for_specific_customer(self):
        self._customer_restriction(
            lambda customer: CustomerVoucher.objects.create(
                customer=customer, voucher=self.voucher
            )
        )

    def test_voucher_for_customer_group(self):
        def restrict(customer):
            group = CustomerGroup.objects.create(name='Special Group')
            customer.groups.add(group)
            CustomerGroupVoucher.objects.create(group=group, voucher=self.voucher)

        self._customer_restriction(restrict)

    # -- What the voucher is used for ------------------------------------------

    def test_voucher_for_specific_class(self):
        ClassVoucher.objects.create(
            classDescription=self.series.classDescription, voucher=self.voucher
        )
        self.assertUsableOnlyFor(self.series, self.other_series)

    def test_voucher_for_dance_type_and_level(self):
        DanceTypeVoucher.objects.create(
            danceTypeLevel=self.levelOne, voucher=self.voucher
        )
        self.assertUsableOnlyFor(self.series, self.other_series)

    def test_voucher_for_series_category(self):
        category = SeriesCategory.objects.create(name='Special Series')
        self.series.category = category
        self.series.save()
        SeriesCategoryVoucher.objects.create(
            seriesCategory=category, voucher=self.voucher
        )
        self.assertUsableOnlyFor(self.series, self.other_series)

    def test_voucher_for_series_category_not_usable_for_public_event(self):
        category = SeriesCategory.objects.create(name='Special Series')
        self.series.category = category
        self.series.save()
        SeriesCategoryVoucher.objects.create(
            seriesCategory=category, voucher=self.voucher
        )
        event = self.create_public_event(
            'Categorized Event',
            category=PublicEventCategory.objects.create(name='Some Events'),
        )
        self.assertVoucherRefused(self.use_voucher(event))

    def test_voucher_for_public_event_category(self):
        category = PublicEventCategory.objects.create(name='Special Events')
        event = self.create_public_event('Special Event', category=category)
        other_event = self.create_public_event('Other Event')
        PublicEventCategoryVoucher.objects.create(
            publicEventCategory=category, voucher=self.voucher
        )
        self.assertUsableOnlyFor(event, other_event)

    def test_voucher_for_session(self):
        session = EventSession.objects.create(name='Special Session', slug='special')
        self.series.session = session
        self.series.save()
        SessionVoucher.objects.create(session=session, voucher=self.voucher)
        self.assertUsableOnlyFor(self.series, self.other_series)

    def test_restricted_voucher_refused_if_any_event_does_not_qualify(self):
        ClassVoucher.objects.create(
            classDescription=self.series.classDescription, voucher=self.voucher
        )
        self.assertVoucherRefused(self.use_voucher(self.series, self.other_series))


class VoucherFormRestrictionsTest(VoucherRestrictionTests, VoucherRestrictionsBase):
    ''' The voucher code is entered on the customer information form. '''
    code_argument = 'gift'


class VoucherCartRestrictionsTest(VoucherRestrictionTests, VoucherRestrictionsBase):
    ''' The voucher code is passed as the discount code of the cart. '''
    code_argument = 'code'
