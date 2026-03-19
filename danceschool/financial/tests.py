"""
This file contains basic tests for the core app.
"""

from django.urls import reverse
from django.conf import settings
from django.utils import timezone

from datetime import timedelta
from dynamic_preferences.registries import global_preferences_registry

from danceschool.core.models import EventOccurrence, EventStaffMember, Series
from danceschool.core.utils.tests import DefaultSchoolTestCase
from danceschool.core.utils.timezone import ensure_localtime

from .helpers import createExpenseItemsForEvents
from .models import (
    ExpenseItem, ExpenseCategory, ExpensePurpose,
    RevenueItem, RevenueCategory, RepeatedExpenseRule,
    StaffMemberWageInfo, TransactionParty,
)


class RevenueTest(DefaultSchoolTestCase):

    def test_revenuesubmission(self):
        """
        Tests that we can log in as a superuser and add a class series
        from the admin form, and that that class shows up on the
        registration page.
        """

        default_rev_cat = RevenueCategory.objects.create(name='Default Category')
        s = self.create_series()

        response = self.client.get(reverse('submitRevenues'))
        self.assertEqual(response.status_code, 302)
        self.client.login(username=self.superuser.username, password='pass')
        response = self.client.get(reverse('submitRevenues'))
        self.assertEqual(response.status_code, 200)

        # Check that association and payment method choices are populated
        self.assertIn(('Cash', 'Cash'), response.context_data.get('form').fields['paymentMethod'].choices)

        # Create a Revenue item that is not associated with a Series/Event for $10
        response = self.client.post(reverse('submitRevenues'), {
            'grossTotal': 10,
            'total': 10,
            'adjustments': 0,
            'fees': 0,
            'category': default_rev_cat.id,
            'description': 'Test Revenue Item',
            'paymentMethod': 'Cash',
            'currentlyHeldBy': self.superuser.id,
            'submissionUser': self.superuser.id,
            'accrualDate': ensure_localtime(timezone.now()).strftime(
                getattr(settings, 'DATETIME_INPUT_FORMATS', ['%Y-%m-%d %H:%M:%S', ])[0]
            ),
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(getattr(response.context_data.get('form', {}), 'errors', None))
        self.assertEqual(response.redirect_chain, [(reverse('submissionRedirect'), 302)])
        self.assertTrue(RevenueItem.objects.filter(description='Test Revenue Item').exists())

        ri = RevenueItem.objects.get(description='Test Revenue Item')

        self.assertEqual(ri.total, 10)
        self.assertEqual(ri.currentlyHeldBy, self.superuser)
        self.assertFalse(ri.event)
        self.assertFalse(ri.received)

        # Create a second Revenue item that is associated with Series s for $20
        response = self.client.post(reverse('submitRevenues'), {
            'grossTotal': 20,
            'total': 20,
            'adjustments': 0,
            'fees': 0,
            'category': default_rev_cat.id,
            'event': s.id,
            'description': 'Test Associated Revenue Item',
            'paymentMethod': 'Cash',
            'currentlyHeldBy': self.superuser.id,
            'submissionUser': self.superuser.id,
            'accrualDate': ensure_localtime(timezone.now()).strftime(
                getattr(settings, 'DATETIME_INPUT_FORMATS', ['%Y-%m-%d %H:%M:%S', ])[0]
            ),
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(getattr(response.context_data.get('form', {}), 'errors', None))
        self.assertEqual(response.redirect_chain, [(reverse('submissionRedirect'), 302)])
        self.assertTrue(RevenueItem.objects.filter(description='Test Associated Revenue Item').exists())

        ri = RevenueItem.objects.get(description='Test Associated Revenue Item')

        self.assertEqual(ri.total, 20)
        self.assertEqual(ri.currentlyHeldBy, self.superuser)
        self.assertEqual(ri.event, s)
        self.assertFalse(ri.received)

    def test_registration_creates_revenue(self):
        """
        Process a registration with a cash payment and ensure that an
        associated RevenueItem is created that links to the Registration's
        Invoice.
        """
        pass


class ExpensesTest(DefaultSchoolTestCase):

    def test_expensesubmission(self):
        """
        Tests that we can log in as a superuser and add an ExpenseItem
        using the Expense submission form.
        """

        default_expense_cat = ExpenseCategory.objects.create(name='Default Category', defaultRate=20)

        response = self.client.get(reverse('submitExpenses'))
        self.assertEqual(response.status_code, 302)
        self.client.login(username=self.superuser.username, password='pass')
        response = self.client.get(reverse('submitExpenses'))
        self.assertEqual(response.status_code, 200)

        # Check that choices are populated for payBy and paymentMethod
        self.assertIn(1, [x[0] for x in response.context_data.get('form').fields['payBy'].choices])
        self.assertIn(('Cash', 'Cash'), response.context_data.get('form').fields['paymentMethod'].choices)

        # Create an expense item for 1 hour of work, paid at default rate ($20)
        response = self.client.post(reverse('submitExpenses'), {
            'hours': 1,
            'category': default_expense_cat.id,
            'payTo': TransactionParty.objects.get_or_create(
                user=self.superuser, defaults={'name': self.superuser.get_full_name()}
            )[0].id,
            'payBy': 1,
            'description': 'Test Expense Item',
            'paymentMethod': 'Cash',
            'reimbursement': False,
            'paid': True,
            'approved': 'Approved',
            'submissionUser': self.superuser.id,
            'accrualDate': ensure_localtime(timezone.now()).strftime(getattr(
                settings, 'DATETIME_INPUT_FORMATS', ['%Y-%m-%d %H:%M:%S', ])[0]
            ),
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(getattr(response.context_data.get('form', {}), 'errors', None))
        self.assertEqual(response.redirect_chain, [(reverse('submissionRedirect'), 302)])
        self.assertTrue(ExpenseItem.objects.filter(description='Test Expense Item').exists())

        ei = ExpenseItem.objects.get(description='Test Expense Item')

        self.assertEqual(ei.total, 20)
        self.assertTrue(ei.approved == 'Approved' and ei.paid)
        self.assertEqual(ei.payTo.user, self.superuser)

        # Create a second expense item for $50, paid to a location
        response = self.client.post(reverse('submitExpenses'), {
            'total': 50,
            'category': default_expense_cat.id,
            'payBy': 2,
            'payTo': TransactionParty.objects.get_or_create(
                location=self.defaultLocation, defaults={'name': self.defaultLocation.name}
            )[0].id,
            'description': 'Test Venue Expense Item',
            'paymentMethod': 'Cash',
            'reimbursement': False,
            'paid': False,
            'approved': '',
            'submissionUser': self.superuser.id,
            'accrualDate': ensure_localtime(timezone.now()).strftime(getattr(
                settings, 'DATETIME_INPUT_FORMATS', ['%Y-%m-%d %H:%M:%S', ])[0]
            ),
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(getattr(response.context_data.get('form', {}), 'errors', None))
        self.assertEqual(response.redirect_chain, [(reverse('submissionRedirect'), 302)])
        self.assertTrue(ExpenseItem.objects.filter(description='Test Venue Expense Item').exists())

        ei = ExpenseItem.objects.get(description='Test Venue Expense Item')

        self.assertEqual(ei.total, 50)
        self.assertFalse(ei.approved or ei.paid)
        self.assertEqual(ei.payTo.location, self.defaultLocation)

    def test_event_creates_teachingexpense(self):
        """
        """
        pass

    def test_event_creates_venueexpense(self):
        """
        Test that venue expenses are reported for
        """
        pass

    def test_substitute_creates_expense(self):
        """
        Report a substitute teacher for a class that has ended and ensure
        that an ExpenseItem associated with that substitute teacher is
        created, and that the existing ExpenseItem associated with the
        existing teacher is updated appropriately
        """
        pass


class FinancialSummariesTest(DefaultSchoolTestCase):

    def create_initial_items(self):
        """
        Create initial revenue items and expense items to test that the
        financial summary views are populated appropriately.
        """
        default_rev_cat = RevenueCategory.objects.create(name='Default Category')
        default_expense_cat = ExpenseCategory.objects.create(name='Default Category', defaultRate=20)

        ei = ExpenseItem.objects.create(
            hours=1,
            category=default_expense_cat,
            approved='Approved',
            paid=True,
            paymentDate=timezone.now(),
            accrualDate=timezone.now(),
        )
        ri = RevenueItem.objects.create(
            total=50,
            category=default_rev_cat,
            accrualDate=timezone.now(),
            received=True,
        )

        return ei, ri

    def test_annual_detailview(self):
        ei, ri = self.create_initial_items()

        response = self.client.get(reverse(
            'financialYearDetailView',
            kwargs={'year': ensure_localtime(timezone.now()).year}
        ))
        self.assertEqual(response.status_code, 302)
        self.client.login(username=self.superuser.username, password='pass')
        response = self.client.get(reverse(
            'financialYearDetailView',
            kwargs={'year': ensure_localtime(timezone.now()).year}
        ))
        self.assertEqual(response.status_code, 200)
        self.assertIn(ei, response.context_data.get('otherExpenseItems'))
        self.assertIn(ri, response.context_data.get('otherRevenueItems'))

        # Change the accrual dates for these items and ensure that
        # they no longer show up
        ei.accrualDate = timezone.now() + timedelta(days=-366)
        ei.save()
        ri.accrualDate = timezone.now() + timedelta(days=-366)
        ri.save()

        response = self.client.get(reverse(
            'financialYearDetailView',
            kwargs={'year': ensure_localtime(timezone.now()).year}
        ))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context_data.get('otherExpenseItems'))
        self.assertFalse(response.context_data.get('otherRevenueItems'))

        # Change the basis to payment/received basis and ensure
        # that the items still show up
        response = self.client.get(reverse(
            'financialYearDetailView',
            kwargs={
                'year': ensure_localtime(timezone.now()).year,
            }
        ) + '?basis=paymentDate')
        self.assertEqual(response.status_code, 200)
        self.assertIn(ei, response.context_data.get('otherExpenseItems'))
        self.assertIn(ri, response.context_data.get('otherRevenueItems'))

    def test_monthly_detailview(self):
        ei, ri = self.create_initial_items()

        response = self.client.get(reverse(
            'financialMonthDetailView',
            kwargs={
                'year': ensure_localtime(timezone.now()).year,
                'month': ensure_localtime(timezone.now()).month
            }
        ))
        self.assertEqual(response.status_code, 302)
        self.client.login(username=self.superuser.username, password='pass')
        response = self.client.get(reverse(
            'financialMonthDetailView',
            kwargs={
                'year': ensure_localtime(timezone.now()).year,
                'month': ensure_localtime(timezone.now()).month
            }
        ))
        self.assertEqual(response.status_code, 200)

        self.assertIn(ei, response.context_data.get('otherExpenseItems'))
        self.assertIn(ri, response.context_data.get('otherRevenueItems'))

        # Change the accrual dates for these items and ensure that
        # they no longer show up
        ei.accrualDate = timezone.now() + timedelta(days=-32)
        ei.save()
        ri.accrualDate = timezone.now() + timedelta(days=-32)
        ri.save()

        response = self.client.get(reverse(
            'financialMonthDetailView',
            kwargs={
                'year': ensure_localtime(timezone.now()).year,
                'month': ensure_localtime(timezone.now()).month
            }
        ))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context_data.get('otherExpenseItems'))
        self.assertFalse(response.context_data.get('otherRevenueItems'))

        # Change the basis to payment/received basis and ensure
        # that the items still show up
        response = self.client.get(
            reverse('financialMonthDetailView', kwargs={
                'year': ensure_localtime(timezone.now()).year,
                'month': ensure_localtime(timezone.now()).month,
            }) + '?basis=paymentDate')
        self.assertEqual(response.status_code, 200)
        self.assertIn(ei, response.context_data.get('otherExpenseItems'))
        self.assertIn(ri, response.context_data.get('otherRevenueItems'))

    def test_summary_bymonth(self):
        s = self.create_series()
        response = self.client.get(reverse('financesByMonth'))
        self.assertEqual(response.status_code, 302)
        self.client.login(username=self.superuser.username, password='pass')
        response = self.client.get(reverse('financesByMonth'))
        self.assertEqual(response.status_code, 200)

    def test_summary_byevent(self):
        s = self.create_series()
        response = self.client.get(reverse('financesByEvent'))
        self.assertEqual(response.status_code, 302)
        self.client.login(username=self.superuser.username, password='pass')
        response = self.client.get(reverse('financesByEvent'))
        self.assertEqual(response.status_code, 200)


class ExpenseItemGenerationTest(DefaultSchoolTestCase):
    '''
    Tests for the three modes of the financial__autoGenerateExpensesEventStaff
    preference: per_event, per_occurrence, and disabled.

    Covers:
     - Basic per-event and per-occurrence item creation
     - Proportional hour distribution across occurrences
     - Idempotency (no duplicates on a second run)
     - Switching from per_event to per_occurrence on a live series
     - Cancelling an occurrence (signal redistributes hours)
     - Non-hourly rules (weekly) are unaffected by the per_occurrence setting
     - Replacement staff causes replaced member's items to be marked unapproved
    '''

    WAGE_RATE = 20.0

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Hourly wage rule for the default instructor (category=None covers all categories)
        cls.hourly_rule = StaffMemberWageInfo.objects.create(
            staffMember=cls.defaultInstructor,
            rentalRate=cls.WAGE_RATE,
            applyRateRule=RepeatedExpenseRule.RateRuleChoices.hourly,
        )

    def _set_pref(self, value):
        gp = global_preferences_registry.manager()
        gp['financial__autoGenerateExpensesEventStaff'] = value

    # ------------------------------------------------------------------
    # Per-event mode
    # ------------------------------------------------------------------

    def test_per_event_creates_one_item_per_staffer(self):
        '''
        In per_event mode, createExpenseItemsForEvents should create exactly
        one ExpenseItem per EventStaffMember, linked via an ExpensePurpose
        with occurrence=None.
        '''
        self._set_pref('per_event')
        s = self.create_series(occurrences=2)
        staffer = EventStaffMember.objects.get(event=s, staffMember=self.defaultInstructor)

        count = createExpenseItemsForEvents()

        self.assertEqual(count, 1)
        purposes = ExpensePurpose.objects.filter(object_id=staffer.pk)
        self.assertEqual(purposes.count(), 1)
        self.assertIsNone(purposes.first().occurrence)

        item = purposes.first().item
        self.assertAlmostEqual(item.hours, staffer.netHours)
        self.assertAlmostEqual(item.total, staffer.netHours * self.WAGE_RATE)

    def test_per_event_is_idempotent(self):
        '''
        Calling createExpenseItemsForEvents twice in per_event mode must not
        create a second expense item for the same staffer/rule.
        '''
        self._set_pref('per_event')
        self.create_series(occurrences=2)

        createExpenseItemsForEvents()
        count_second = createExpenseItemsForEvents()

        self.assertEqual(count_second, 0)
        self.assertEqual(ExpenseItem.objects.filter(expenseRule=self.hourly_rule).count(), 1)

    # ------------------------------------------------------------------
    # Per-occurrence mode
    # ------------------------------------------------------------------

    def test_per_occurrence_creates_one_item_per_occurrence(self):
        '''
        In per_occurrence mode, one ExpenseItem must be created per
        EventOccurrence per EventStaffMember, each with its ExpensePurpose
        occurrence field set.
        '''
        self._set_pref('per_occurrence')
        s = self.create_series(occurrences=2)
        staffer = EventStaffMember.objects.get(event=s, staffMember=self.defaultInstructor)

        count = createExpenseItemsForEvents()

        self.assertEqual(count, 2)
        purposes = ExpensePurpose.objects.filter(object_id=staffer.pk)
        self.assertEqual(purposes.count(), 2)
        # Every purpose must have an occurrence set
        self.assertTrue(all(p.occurrence is not None for p in purposes))
        # The two linked occurrences must be the event's two occurrences
        occ_pks = set(p.occurrence_id for p in purposes)
        event_occ_pks = set(s.eventoccurrence_set.values_list('pk', flat=True))
        self.assertEqual(occ_pks, event_occ_pks)

    def test_per_occurrence_hours_sum_to_net(self):
        '''
        The sum of hours across all per-occurrence items for a single staffer
        must equal the staffer's netHours.
        '''
        self._set_pref('per_occurrence')
        s = self.create_series(occurrences=3)
        staffer = EventStaffMember.objects.get(event=s, staffMember=self.defaultInstructor)

        createExpenseItemsForEvents()

        items = ExpenseItem.objects.filter(
            expensepurpose__object_id=staffer.pk,
            expenseRule=self.hourly_rule,
        )
        total_hours = sum(i.hours for i in items)
        self.assertAlmostEqual(total_hours, staffer.netHours, places=5)

    def test_per_occurrence_equal_duration_proportional_hours(self):
        '''
        With N equal-duration occurrences each staffer gets netHours/N hours
        per occurrence item.
        '''
        self._set_pref('per_occurrence')
        n = 3
        s = self.create_series(occurrences=n)
        staffer = EventStaffMember.objects.get(event=s, staffMember=self.defaultInstructor)
        expected_per_occ = staffer.netHours / n

        createExpenseItemsForEvents()

        items = ExpenseItem.objects.filter(
            expensepurpose__object_id=staffer.pk,
            expenseRule=self.hourly_rule,
        )
        for item in items:
            self.assertAlmostEqual(item.hours, expected_per_occ, places=5)
            self.assertAlmostEqual(item.total, expected_per_occ * self.WAGE_RATE, places=5)

    def test_per_occurrence_unequal_duration_proportional_hours(self):
        '''
        When occurrences have unequal durations, each item's hours are
        proportional to that occurrence's share of total duration.
        '''
        from danceschool.core.constants import getConstant

        self._set_pref('per_occurrence')
        # Build the series manually so we control exactly which occurrences exist.
        s = Series.objects.create(
            classDescription=self.levelOneClassDescription,
            pricingTier=self.defaultPricing,
            location=self.defaultLocation,
        )
        now = timezone.now() + timedelta(days=1)
        occ1 = EventOccurrence.objects.create(
            event=s, startTime=now, endTime=now + timedelta(hours=1)
        )
        occ2 = EventOccurrence.objects.create(
            event=s, startTime=now + timedelta(days=1),
            endTime=now + timedelta(days=1, hours=2)
        )
        staffer = EventStaffMember.objects.create(
            event=s,
            category=getConstant('general__eventStaffCategoryInstructor'),
            staffMember=self.defaultInstructor,
        )
        staffer.occurrences.set([occ1, occ2])

        createExpenseItemsForEvents()

        purposes = ExpensePurpose.objects.filter(object_id=staffer.pk)
        self.assertEqual(purposes.count(), 2)

        hours_by_occ = {p.occurrence_id: p.item.hours for p in purposes}
        # occ1 is 1h out of 3h total → 1/3 of netHours
        # occ2 is 2h out of 3h total → 2/3 of netHours
        net = staffer.netHours
        self.assertAlmostEqual(hours_by_occ[occ1.pk], net / 3, places=5)
        self.assertAlmostEqual(hours_by_occ[occ2.pk], 2 * net / 3, places=5)

    def test_per_occurrence_is_idempotent(self):
        '''
        Calling createExpenseItemsForEvents twice in per_occurrence mode must
        not create duplicate items for already-covered occurrences.
        '''
        self._set_pref('per_occurrence')
        self.create_series(occurrences=2)

        createExpenseItemsForEvents()
        count_second = createExpenseItemsForEvents()

        self.assertEqual(count_second, 0)
        self.assertEqual(ExpenseItem.objects.filter(expenseRule=self.hourly_rule).count(), 2)

    # ------------------------------------------------------------------
    # Switching modes on a live series
    # ------------------------------------------------------------------

    def test_switch_per_event_to_per_occurrence_preserves_old_items(self):
        '''
        When the preference changes from per_event to per_occurrence for a
        series that already has per-event items, the old per-event items must
        remain and new per-occurrence items must be created alongside them.
        '''
        s = self.create_series(occurrences=2)
        staffer = EventStaffMember.objects.get(event=s, staffMember=self.defaultInstructor)

        # First run in per_event mode
        self._set_pref('per_event')
        createExpenseItemsForEvents()
        self.assertEqual(ExpenseItem.objects.filter(expenseRule=self.hourly_rule).count(), 1)

        # Switch to per_occurrence and run again
        self._set_pref('per_occurrence')
        new_count = createExpenseItemsForEvents()

        self.assertEqual(new_count, 2)
        all_items = ExpenseItem.objects.filter(expenseRule=self.hourly_rule)
        # One old per-event item + two new per-occurrence items
        self.assertEqual(all_items.count(), 3)

        purposes = ExpensePurpose.objects.filter(object_id=staffer.pk)
        occ_none = [p for p in purposes if p.occurrence is None]
        occ_set = [p for p in purposes if p.occurrence is not None]
        self.assertEqual(len(occ_none), 1, 'Original per-event purpose must still exist')
        self.assertEqual(len(occ_set), 2, 'Two per-occurrence purposes must have been created')

    # ------------------------------------------------------------------
    # Cancelled occurrence
    # ------------------------------------------------------------------

    def test_cancelled_occurrence_zeroes_its_expense_item(self):
        '''
        When an EventOccurrence is cancelled, the post_save signal handler
        must set its linked per-occurrence expense item's hours to 0.

        Without specifiedHours, the total hours shrink to match only the
        remaining non-cancelled occurrences (the allocation is recalculated
        from the sum of non-cancelled durations).
        '''
        self._set_pref('per_occurrence')
        s = self.create_series(occurrences=2)  # two equal 1-hour occurrences
        staffer = EventStaffMember.objects.get(event=s, staffMember=self.defaultInstructor)
        occs = list(s.eventoccurrence_set.order_by('startTime'))

        createExpenseItemsForEvents()

        # Each occurrence should start with 1 hour each
        for purpose in ExpensePurpose.objects.filter(object_id=staffer.pk):
            self.assertAlmostEqual(purpose.item.hours, 1.0, places=5)

        # Cancel the first occurrence — signal fires automatically via post_save
        occ_to_cancel = occs[0]
        occ_to_cancel.cancelled = True
        occ_to_cancel.save()

        # Cancelled occurrence's item must now have hours=0
        cancelled_purpose = ExpensePurpose.objects.get(
            object_id=staffer.pk, occurrence=occ_to_cancel
        )
        cancelled_purpose.item.refresh_from_db()
        self.assertAlmostEqual(cancelled_purpose.item.hours, 0.0, places=5)

        # Without specifiedHours, total is the sum of non-cancelled durations.
        # The one remaining 1-hour occurrence keeps its 1.0 h (not 2.0).
        remaining_purpose = ExpensePurpose.objects.get(
            object_id=staffer.pk, occurrence=occs[1]
        )
        remaining_purpose.item.refresh_from_db()
        self.assertAlmostEqual(remaining_purpose.item.hours, 1.0, places=5)

    def test_cancelled_occurrence_redistributes_specified_hours(self):
        '''
        When specifiedHours is set on the staffer, the total hours are fixed.
        Cancelling one occurrence redistributes those fixed hours to the
        remaining occurrence(s).
        '''
        from danceschool.core.constants import getConstant

        self._set_pref('per_occurrence')
        s = Series.objects.create(
            classDescription=self.levelOneClassDescription,
            pricingTier=self.defaultPricing,
            location=self.defaultLocation,
        )
        now = timezone.now() + timedelta(days=1)
        occ1 = EventOccurrence.objects.create(
            event=s, startTime=now, endTime=now + timedelta(hours=1)
        )
        occ2 = EventOccurrence.objects.create(
            event=s, startTime=now + timedelta(days=1),
            endTime=now + timedelta(days=1, hours=1)
        )
        # specifiedHours=4 regardless of occurrence count
        staffer = EventStaffMember.objects.create(
            event=s,
            category=getConstant('general__eventStaffCategoryInstructor'),
            staffMember=self.defaultInstructor,
            specifiedHours=4.0,
        )
        staffer.occurrences.set([occ1, occ2])

        createExpenseItemsForEvents()

        # Each occurrence gets 2 hours (4h split evenly)
        for purpose in ExpensePurpose.objects.filter(object_id=staffer.pk):
            self.assertAlmostEqual(purpose.item.hours, 2.0, places=5)

        # Cancel occ1 — the remaining occ2 must now absorb all 4 fixed hours
        occ1.cancelled = True
        occ1.save()

        cancelled_purpose = ExpensePurpose.objects.get(object_id=staffer.pk, occurrence=occ1)
        cancelled_purpose.item.refresh_from_db()
        self.assertAlmostEqual(cancelled_purpose.item.hours, 0.0, places=5)

        remaining_purpose = ExpensePurpose.objects.get(object_id=staffer.pk, occurrence=occ2)
        remaining_purpose.item.refresh_from_db()
        self.assertAlmostEqual(remaining_purpose.item.hours, 4.0, places=5)

    # ------------------------------------------------------------------
    # Non-hourly rules
    # ------------------------------------------------------------------

    def test_non_hourly_rule_unaffected_by_per_occurrence_preference(self):
        '''
        Non-hourly (e.g. weekly) rules always go through the time-window path
        regardless of the per_occurrence preference, so their ExpensePurpose
        records must have occurrence=None.
        '''
        # Create a second instructor so we can add a weekly rule without
        # conflicting with the hourly_rule's unique_together constraint.
        norma = self.create_instructor(firstName='Norma', lastName='Miller')
        weekly_rule = StaffMemberWageInfo.objects.create(
            staffMember=norma,
            rentalRate=100.0,
            applyRateRule=RepeatedExpenseRule.RateRuleChoices.weekly,
        )

        self._set_pref('per_occurrence')
        s = self.create_series(occurrences=2, instructors=[norma])

        createExpenseItemsForEvents()

        purposes = ExpensePurpose.objects.filter(
            item__expenseRule=weekly_rule,
        )
        self.assertGreater(purposes.count(), 0, 'Weekly rule must have created at least one item')
        for p in purposes:
            self.assertIsNone(
                p.occurrence,
                'Non-hourly expense purposes must not be linked to a specific occurrence',
            )

    # ------------------------------------------------------------------
    # Replacement staff
    # ------------------------------------------------------------------

    def test_replacement_staff_unapproves_replaced_per_occurrence_items(self):
        '''
        When a substitute EventStaffMember is created with replacedStaffMember
        set, the post_save signal must set approved=None on all per-occurrence
        expense items belonging to the replaced staff member.
        '''
        self._set_pref('per_occurrence')
        s = self.create_series(occurrences=2)
        original_staffer = EventStaffMember.objects.get(
            event=s, staffMember=self.defaultInstructor
        )

        createExpenseItemsForEvents()

        # Manually approve the original staffer's expense items
        for purpose in original_staffer.related_expenses.filter(occurrence__isnull=False):
            purpose.item.approved = 'Approved'
            purpose.item.save()

        # Create a substitute for the original staffer
        norma = self.create_instructor(firstName='Norma', lastName='Miller')
        substitute = EventStaffMember.objects.create(
            event=s,
            category=original_staffer.category,
            staffMember=norma,
            replacedStaffMember=original_staffer,
        )
        # Assign the substitute to one of the occurrences
        substitute.occurrences.add(s.eventoccurrence_set.first())

        # The signal fired on substitute.save() should have cleared approval
        for purpose in original_staffer.related_expenses.filter(occurrence__isnull=False):
            purpose.item.refresh_from_db()
            self.assertIsNone(
                purpose.item.approved,
                'Replaced staffer\'s per-occurrence items must be marked unapproved',
            )
