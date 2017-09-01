"""
This file contains basic tests for the core app.
"""

from django.core.urlresolvers import reverse
from django.conf import settings
from django.utils import timezone

from datetime import timedelta

from danceschool.core.utils.tests import DefaultSchoolTestCase
from danceschool.core.utils.timezone import ensure_localtime

from .models import ExpenseItem, ExpenseCategory, RevenueItem, RevenueCategory


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
        self.client.login(username=self.superuser.username,password='pass')
        response = self.client.get(reverse('submitRevenues'))
        self.assertEqual(response.status_code, 200)

        # Check that association and payment method choices are populated
        self.assertIn(('Cash','Cash'), response.context_data.get('form').fields['paymentMethod'].choices)
        self.assertIn(3, [x[0] for x in response.context_data.get('form').fields['associateWith'].choices])

        # Create a Revenue item that is not associated with a Series/Event for $10
        response = self.client.post(reverse('submitRevenues'),{
            'total': 10,
            'category': default_rev_cat.id,
            'associateWith': 3,
            'description': 'Test Revenue Item',
            'paymentMethod': 'Cash',
            'currentlyHeldBy': self.superuser.id,
            'submissionUser': self.superuser.id,
            'accrualDate': ensure_localtime(timezone.now()).strftime(getattr(settings,'DATETIME_INPUT_FORMATS',['%Y-%m-%d %H:%M:%S',])[0]),
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(getattr(response.context_data.get('form',{}),'errors',None))
        self.assertEqual(response.redirect_chain,[(reverse('submissionRedirect'),302)])
        self.assertTrue(RevenueItem.objects.filter(description='Test Revenue Item').exists())

        ri = RevenueItem.objects.get(description='Test Revenue Item')

        self.assertEqual(ri.total, 10)
        self.assertEqual(ri.currentlyHeldBy, self.superuser)
        self.assertFalse(ri.event)
        self.assertFalse(ri.received)

        # Create a second Revenue item that is associated with Series s for $20
        response = self.client.post(reverse('submitRevenues'),{
            'total': 20,
            'category': default_rev_cat.id,
            'associateWith': 2,
            'event': s.id,
            'description': 'Test Associated Revenue Item',
            'paymentMethod': 'Cash',
            'currentlyHeldBy': self.superuser.id,
            'submissionUser': self.superuser.id,
            'accrualDate': ensure_localtime(timezone.now()).strftime(getattr(settings,'DATETIME_INPUT_FORMATS',['%Y-%m-%d %H:%M:%S',])[0]),
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(getattr(response.context_data.get('form',{}),'errors',None))
        self.assertEqual(response.redirect_chain,[(reverse('submissionRedirect'),302)])
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

        default_expense_cat = ExpenseCategory.objects.create(name='Default Category',defaultRate=20)

        response = self.client.get(reverse('submitExpenses'))
        self.assertEqual(response.status_code, 302)
        self.client.login(username=self.superuser.username,password='pass')
        response = self.client.get(reverse('submitExpenses'))
        self.assertEqual(response.status_code, 200)

        # Check that choices are populated for payTo, payBy, and paymentMethod
        self.assertIn(1, [x[0] for x in response.context_data.get('form').fields['payTo'].choices])
        self.assertIn(1, [x[0] for x in response.context_data.get('form').fields['payBy'].choices])
        self.assertIn(('Cash','Cash'), response.context_data.get('form').fields['paymentMethod'].choices)

        # Create an expense item for 1 hour of work, paid at default rate ($20)
        response = self.client.post(reverse('submitExpenses'),{
            'hours': 1,
            'category': default_expense_cat.id,
            'payTo': 1,
            'payToUser': self.superuser.id,
            'payBy': 1,
            'description': 'Test Expense Item',
            'paymentMethod': 'Cash',
            'reimbursement': False,
            'paid': True,
            'approved': True,
            'submissionUser': self.superuser.id,
            'accrualDate': ensure_localtime(timezone.now()).strftime(getattr(settings,'DATETIME_INPUT_FORMATS',['%Y-%m-%d %H:%M:%S',])[0]),
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(getattr(response.context_data.get('form',{}),'errors',None))
        self.assertEqual(response.redirect_chain,[(reverse('submissionRedirect'),302)])
        self.assertTrue(ExpenseItem.objects.filter(description='Test Expense Item').exists())

        ei = ExpenseItem.objects.get(description='Test Expense Item')

        self.assertEqual(ei.total, 20)
        self.assertTrue(ei.approved and ei.paid)
        self.assertEqual(ei.payToUser, self.superuser)

        # Create a second expense item for $50, paid to a location
        response = self.client.post(reverse('submitExpenses'),{
            'total': 50,
            'category': default_expense_cat.id,
            'payTo': 2,
            'payBy': 2,
            'payToLocation': self.defaultLocation.id,
            'description': 'Test Venue Expense Item',
            'paymentMethod': 'Cash',
            'reimbursement': False,
            'paid': False,
            'approved': False,
            'submissionUser': self.superuser.id,
            'accrualDate': ensure_localtime(timezone.now()).strftime(getattr(settings,'DATETIME_INPUT_FORMATS',['%Y-%m-%d %H:%M:%S',])[0]),
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(getattr(response.context_data.get('form',{}),'errors',None))
        self.assertEqual(response.redirect_chain,[(reverse('submissionRedirect'),302)])
        self.assertTrue(ExpenseItem.objects.filter(description='Test Venue Expense Item').exists())

        ei = ExpenseItem.objects.get(description='Test Venue Expense Item')

        self.assertEqual(ei.total, 50)
        self.assertFalse(ei.approved or ei.paid)
        self.assertEqual(ei.payToLocation, self.defaultLocation)

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
        default_expense_cat = ExpenseCategory.objects.create(name='Default Category',defaultRate=20)

        ei = ExpenseItem.objects.create(
            hours=1,
            category=default_expense_cat,
            approved=True,
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

        response = self.client.get(reverse('financialDetailView'),{'year': ensure_localtime(timezone.now()).year})
        self.assertEqual(response.status_code, 302)
        self.client.login(username=self.superuser.username,password='pass')
        response = self.client.get(reverse('financialDetailView'),{'year': ensure_localtime(timezone.now()).year})
        self.assertEqual(response.status_code, 200)
        self.assertIn(ei, response.context_data.get('otherExpenseItems'))
        self.assertIn(ri, response.context_data.get('otherRevenueItems'))

        # Change the accrual dates for these items and ensure that
        # they no longer show up
        ei.accrualDate = timezone.now() + timedelta(days=-366)
        ei.save()
        ri.accrualDate = timezone.now() + timedelta(days=-366)
        ri.save()

        response = self.client.get(reverse('financialDetailView'),{'year': ensure_localtime(timezone.now()).year})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context_data.get('otherExpenseItems'))
        self.assertFalse(response.context_data.get('otherRevenueItems'))

        # Change the basis to payment/received basis and ensure
        # that the items still show up
        response = self.client.get(reverse('financialDetailView'),{'year': ensure_localtime(timezone.now()).year, 'basis': 'paymentDate'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(ei, response.context_data.get('otherExpenseItems'))
        self.assertIn(ri, response.context_data.get('otherRevenueItems'))

    def test_monthly_detailview(self):
        ei, ri = self.create_initial_items()

        response = self.client.get(reverse('financialDetailView'),{'year': ensure_localtime(timezone.now()).year, 'month': ensure_localtime(timezone.now()).month})
        self.assertEqual(response.status_code, 302)
        self.client.login(username=self.superuser.username,password='pass')
        response = self.client.get(reverse('financialDetailView'),{'year': ensure_localtime(timezone.now()).year, 'month': ensure_localtime(timezone.now()).month})
        self.assertEqual(response.status_code, 200)

        self.assertIn(ei, response.context_data.get('otherExpenseItems'))
        self.assertIn(ri, response.context_data.get('otherRevenueItems'))

        # Change the accrual dates for these items and ensure that
        # they no longer show up
        ei.accrualDate = timezone.now() + timedelta(days=-32)
        ei.save()
        ri.accrualDate = timezone.now() + timedelta(days=-32)
        ri.save()

        response = self.client.get(reverse('financialDetailView'),{'year': ensure_localtime(timezone.now()).year, 'month': ensure_localtime(timezone.now()).month})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context_data.get('otherExpenseItems'))
        self.assertFalse(response.context_data.get('otherRevenueItems'))

        # Change the basis to payment/received basis and ensure
        # that the items still show up
        response = self.client.get(reverse('financialDetailView'),{'year': ensure_localtime(timezone.now()).year, 'month': ensure_localtime(timezone.now()).month, 'basis': 'paymentDate'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(ei, response.context_data.get('otherExpenseItems'))
        self.assertIn(ri, response.context_data.get('otherRevenueItems'))

    def test_summary_bymonth(self):
        s = self.create_series()
        response = self.client.get(reverse('financesByMonth'))
        self.assertEqual(response.status_code, 302)
        self.client.login(username=self.superuser.username,password='pass')
        response = self.client.get(reverse('financesByMonth'))
        self.assertEqual(response.status_code, 200)

    def test_summary_byevent(self):
        s = self.create_series()
        response = self.client.get(reverse('financesByEvent'))
        self.assertEqual(response.status_code, 302)
        self.client.login(username=self.superuser.username,password='pass')
        response = self.client.get(reverse('financesByEvent'))
        self.assertEqual(response.status_code, 200)
