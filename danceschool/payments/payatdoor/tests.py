"""
This file contains tests for at-the-door (e.g. cash) payments
"""

from django.urls import reverse
from django.conf import settings

from cms.api import create_page, add_plugin, publish_page
from cms.models import StaticPlaceholder

from danceschool.core.models import Registration, Invoice
from danceschool.core.constants import REG_VALIDATION_STR
from danceschool.core.utils.tests import DefaultSchoolTestCase

# from .cms_plugins import PayAtDoorFormPlugin
from .constants import ATTHEDOOR_PAYMENTMETHOD_CHOICES


class PayAtDoorTest(DefaultSchoolTestCase):

    def test_payment_at_door(self):
        """
        Tests that a payment at the door can be submitted, the invoice is marked
        as paid, and the associated registration is finalized.
        """

        # Add the at-the-door payment CMS plugin
        payatdoor_sp = StaticPlaceholder.objects.get_or_create(code='registration_payatdoor_placeholder')
        payatdoor_p_draft = payatdoor_sp[0].draft
        payatdoor_p_public = payatdoor_sp[0].public

        try:
            initial_language = settings.LANGUAGES[0][0]
        except IndexError:
            initial_language = getattr(settings, 'LANGUAGE_CODE', 'en')

        add_plugin(
            payatdoor_p_draft, 'PayAtDoorFormPlugin', initial_language,
        )
        add_plugin(
            payatdoor_p_public, 'PayAtDoorFormPlugin', initial_language,
        )

        # Log in as the superuser so that we can conduct a registration at the
        # door and check that the option for an at-the-door payment is
        # available.
        self.client.login(username=self.superuser.username, password='pass')

        # Add a class series with occurrences in the future, and check that
        # registration is open by looking at the registration page
        s = self.create_series()
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerysetEqual(response.context_data['regOpenSeries'], [s.__repr__(), ])

        # Since the superuser is logged in, check that there is an option to 
        # register at the door
        self.assertTrue(response.context_data['form'].fields.get('payAtDoor'))

        # Sign up for the series, and check that we proceed to the student information page.
        # Because of the way that roles are encoded on this form, we just grab the value to pass
        # from the form itself.
        post_data = {
            'series_%s' % s.id: response.context_data['form'].fields['series_%s' % s.id].choices[0][0],
            'payAtDoor': True,
        }

        response = self.client.post(reverse('registration'), post_data, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse('getStudentInfo'), 302)])

        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR].get('invoiceId')
        )
        tr = Registration.objects.filter(invoice=invoice).first()
        self.assertTrue(tr.eventregistration_set.filter(event__id=s.id).exists())
        self.assertFalse(tr.final)
        self.assertEqual(tr.payAtDoor, True)

        # Check that the student info page lists the correct item amounts and subtotal
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(response.context_data.get('invoice').total, s.getBasePrice())

        # Sign up for the series
        post_data = {
            'firstName': 'Test',
            'lastName': 'Customer',
            'email': 'test@customer.com',
            'agreeToPolicies': True,
        }
        response = self.register_to_check_discount(s)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])

        # Since there are no discounts or vouchers applied, check that the net price
        # and gross price match.
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 0)

        # Check that the option to pay at the door is available.
        self.assertContains(response, '<form id="payatdoor-payment-form"')

        invoice = response.context_data.get('invoice')
        registration = response.context_data.get('registration')

        # Submit an at-the-door payment.
        post_data = {
            'submissionUser': self.superuser.id,
            'registration': registration.id,
            'invoice': str(invoice.id),
            'amountPaid': invoice.total,
            'paymentMethod': ATTHEDOOR_PAYMENTMETHOD_CHOICES[0][0],
            'payerEmail': self.superuser.email,
            'receivedBy': self.superuser.id,
        }

        response = self.client.post(reverse('doorPaymentHandler'), post_data, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse('registration'), 302)])

        invoice.refresh_from_db()
        registration.refresh_from_db()

        self.assertEqual(invoice.status, invoice.PaymentStatus.paid)
        self.assertEqual(invoice.outstandingBalance, 0)
        self.assertTrue(registration.final)

    def test_willpay_at_door(self):
        """
        Tests that a commitment to pay at the door can be submitted, the invoice
        is marked as unpaid, and the associated registration is finalized.
        """

        try:
            initial_language = settings.LANGUAGES[0][0]
        except IndexError:
            initial_language = getattr(settings, 'LANGUAGE_CODE', 'en')

        home_page = create_page(
            'Home', 'cms/frontpage.html', initial_language,
            menu_title='Home', in_navigation=True, published=True
        )
        publish_page(home_page, self.superuser, initial_language)
        home_page.set_as_homepage()

        # Add the at-the-door will pay CMS plugin
        payment_sp = StaticPlaceholder.objects.get_or_create(code='registration_payment_placeholder')
        payment_p_draft = payment_sp[0].draft
        payment_p_public = payment_sp[0].public

        add_plugin(
            payment_p_draft, 'WillPayAtDoorFormPlugin', initial_language,
            successPage=home_page,
        )
        add_plugin(
            payment_p_public, 'WillPayAtDoorFormPlugin', initial_language,
            successPage=home_page,
        )

        # Add a class series with occurrences in the future, and check that
        # registration is open by looking at the registration page
        s = self.create_series()
        response = self.client.get(reverse('registration'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerysetEqual(response.context_data['regOpenSeries'], [s.__repr__(), ])

        # Since no one is logged in, check that there is not an option to
        # pay at the door
        self.assertFalse(response.context_data['form'].fields.get('payAtDoor'))

        # Sign up for the series, and check that we proceed to the student information page.
        # Because of the way that roles are encoded on this form, we just grab the value to pass
        # from the form itself.
        post_data = {
            'series_%s' % s.id: response.context_data['form'].fields['series_%s' % s.id].choices[0][0],
        }

        response = self.client.post(reverse('registration'), post_data, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse('getStudentInfo'), 302)])

        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR].get('invoiceId')
        )
        tr = Registration.objects.filter(invoice=invoice).first()
        self.assertTrue(tr.eventregistration_set.filter(event__id=s.id).exists())
        self.assertFalse(tr.final)
        self.assertEqual(tr.payAtDoor, False)

        # Check that the student info page lists the correct item amounts and subtotal
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(response.context_data.get('invoice').total, s.getBasePrice())

        # Sign up for the series
        post_data = {
            'firstName': 'Test',
            'lastName': 'Customer',
            'email': 'test@customer.com',
            'agreeToPolicies': True,
        }
        response = self.register_to_check_discount(s)
        invoice = response.context_data.get('invoice')
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])

        # Since there are no discounts or vouchers applied, check that the net price
        # and gross price match.
        self.assertEqual(invoice.grossTotal, s.getBasePrice())
        self.assertEqual(
            invoice.total, invoice.grossTotal
        )
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 0)

        # Check that the option to say you will pay at the door is available.
        self.assertContains(response, '<div id="div_id_willPayAtDoor"')

        invoice = response.context_data.get('invoice')
        registration = response.context_data.get('registration')

        # Submit an at-the-door payment.
        post_data = {
            'invoice': str(invoice.id),
            'instance': payment_p_public.get_plugins().first().id,
            'willPayAtDoor': True,
        }

        response = self.client.post(reverse('doorWillPayHandler'), post_data, follow=True)
        self.assertEqual(response.redirect_chain, [(home_page.get_absolute_url(), 302)])

        invoice.refresh_from_db()
        registration.refresh_from_db()

        self.assertEqual(invoice.status, invoice.PaymentStatus.unpaid)
        self.assertEqual(invoice.outstandingBalance, s.getBasePrice())
        self.assertTrue(registration.final)
