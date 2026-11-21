"""
This file contains tests for at-the-door (e.g. cash) payments
"""

import json

from django.urls import reverse
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.contrib.messages import get_messages
from django.core import mail
from django.db import transaction

from dynamic_preferences.registries import global_preferences_registry

from cms.api import add_plugin
from cms.models import PageContent

from djangocms_alias.models import Alias, AliasContent, Category
from djangocms_alias.constants import DEFAULT_STATIC_ALIAS_CATEGORY_NAME
from djangocms_versioning.constants import PUBLISHED
from djangocms_versioning.models import Version

from danceschool.core.models import Registration, Invoice
from danceschool.core.constants import REG_VALIDATION_STR
from danceschool.core.tests.defaults import DefaultSchoolTestCase

# from .cms_plugins import PayAtDoorFormPlugin
from .constants import ATTHEDOOR_PAYMENTMETHOD_CHOICES
from .forms import DoorPaymentForm


def _get_or_create_alias_with_content(static_code, language, user):
    """
    CMS 5 replacement for ``StaticPlaceholder.objects.get_or_create(code=...)``.

    The pre-CMS-4 ``StaticPlaceholder`` model with ``.draft``/``.public``
    accessors was replaced by ``djangocms_alias.Alias`` + ``AliasContent``,
    with publishing state tracked via ``djangocms_versioning.Version``. We
    return a single ``AliasContent`` (no draft/public split) with its
    placeholder ready to receive plugins.
    """
    alias_category = Category.objects.filter(
        translations__name=DEFAULT_STATIC_ALIAS_CATEGORY_NAME
    ).first()
    if not alias_category:
        alias_category = Category.objects.create(name=DEFAULT_STATIC_ALIAS_CATEGORY_NAME)

    # The templates use {% static_alias ... site %}, which looks for an alias
    # for the current site.
    alias, _ = Alias.objects.get_or_create(
        static_code=static_code, site=Site.objects.get_current(),
        defaults={
            'category': alias_category,
            'creation_method': Alias.CREATION_BY_TEMPLATE,
        },
    )
    alias_content, _ = AliasContent.objects.get_or_create(
        alias=alias, language=language,
        defaults={'name': static_code},
    )
    Version.objects.get_or_create(
        content_type=ContentType.objects.get_for_model(AliasContent),
        object_id=alias_content.pk,
        defaults={'state': PUBLISHED, 'created_by': user},
    )
    return alias_content


def _create_versioned_home_page(language, user, school_name='Test School'):
    """
    CMS 5 replacement for ``create_page(..., published=True)`` + ``publish_page()``.

    See ``danceschool.core.management.commands.setupschool.SetupMixin
    .create_versioned_page`` for the production version of this pattern.
    """
    from cms.api import create_page

    page = create_page(
        title='Home', template='cms/frontpage.html', language=language,
        menu_title='Home', in_navigation=True,
    )
    page_content = PageContent.admin_manager.get(page=page, language=language)
    Version.objects.get_or_create(
        content_type=ContentType.objects.get_for_model(PageContent),
        object_id=page_content.pk,
        defaults={'state': PUBLISHED, 'created_by': user},
    )
    with transaction.atomic():
        page.set_as_homepage()
    return page


class PayAtDoorTest(DefaultSchoolTestCase):
    '''
    A registration through the cart, followed by a payment at the door (by
    staff) or a commitment to pay at the door (by the customer).
    '''

    def setUp(self):
        try:
            self.language = settings.LANGUAGES[0][0]
        except IndexError:
            self.language = getattr(settings, 'LANGUAGE_CODE', 'en')

    def checkout(self, series, payAtDoor=False):
        '''
        Put a registration for the series in the cart and check out, then
        enter the customer's information.  Returns the response for the
        registration summary page.
        '''
        cart_data = {
            'items': [{
                'item_type': 'Event', 'item_id': series.id,
                'sku': 'EVENT_{}_GENERAL'.format(series.id), 'quantity': 1,
            }],
            'checkout': True,
        }
        if payAtDoor:
            cart_data['payAtDoor'] = True

        response = self.client.post(
            reverse('cart'), data=json.dumps(cart_data),
            content_type='application/json', follow=True,
        )
        self.assertEqual(response.redirect_chain, [(reverse('getStudentInfo'), 302)])

        invoice = Invoice.objects.get(
            id=self.client.session[REG_VALIDATION_STR].get('invoice_id')
        )
        registration = Registration.objects.filter(invoice=invoice).first()
        self.assertTrue(registration.eventregistration_set.filter(event__id=series.id).exists())
        self.assertFalse(registration.final)
        self.assertEqual(registration.payAtDoor, payAtDoor)

        # The student info page lists the price of the series.
        price = series.getBasePrice(payAtDoor=payAtDoor)
        self.assertEqual(invoice.grossTotal, price)
        self.assertEqual(response.context_data.get('invoice').total, price)

        response = self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Test',
            'lastName': 'Customer',
            'email': 'test@customer.com',
            'agreeToPolicies': True,
        }, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse('showRegSummary'), 302)])

        # There are no discounts or vouchers, so the net price is the gross price.
        invoice = response.context_data.get('invoice')
        self.assertEqual(invoice.grossTotal, price)
        self.assertEqual(invoice.total, invoice.grossTotal)
        self.assertEqual(response.context_data.get('zero_balance'), False)
        self.assertEqual(response.context_data.get('total_discount_amount'), 0)
        return response

    def test_door_registration_requires_permission(self):
        ''' A customer cannot check out as an at-the-door registration. '''
        s = self.create_series()
        response = self.client.post(
            reverse('cart'), content_type='application/json', data=json.dumps({
                'items': [{
                    'item_type': 'Event', 'item_id': s.id,
                    'sku': 'EVENT_{}_GENERAL'.format(s.id), 'quantity': 1,
                }],
                'checkout': True, 'payAtDoor': True,
            }),
        )
        self.assertEqual(response.status_code, 403)

    def test_payment_at_door(self):
        """
        Tests that a payment at the door can be submitted, the invoice is marked
        as paid, and the associated registration is finalized.
        """

        # Add the at-the-door payment CMS plugin to the alias placeholder
        payatdoor_alias_content = _get_or_create_alias_with_content(
            'registration_payatdoor_placeholder', self.language, self.superuser,
        )
        add_plugin(
            payatdoor_alias_content.placeholder, 'PayAtDoorFormPlugin', self.language,
        )

        # Staff (here, the superuser) may register at the door.
        self.client.login(username=self.superuser.username, password='pass')
        s = self.create_series()
        response = self.checkout(s, payAtDoor=True)

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

        home_page = _create_versioned_home_page(self.language, self.superuser)

        # Add the at-the-door will pay CMS plugin to the alias placeholder
        payment_alias_content = _get_or_create_alias_with_content(
            'registration_payment_placeholder', self.language, self.superuser,
        )
        add_plugin(
            payment_alias_content.placeholder, 'WillPayAtDoorFormPlugin', self.language,
            successPage=home_page,
        )

        # A customer (not logged in) registers online.
        s = self.create_series()
        response = self.checkout(s)

        # Check that the option to say you will pay at the door is available.
        self.assertContains(response, '<div id="div_id_willPayAtDoor"')

        invoice = response.context_data.get('invoice')
        registration = response.context_data.get('registration')

        # Submit an at-the-door payment.
        post_data = {
            'invoice': str(invoice.id),
            'instance': payment_alias_content.placeholder.get_plugins().first().id,
            'willPayAtDoor': True,
        }

        response = self.client.post(reverse('doorWillPayHandler'), post_data, follow=True)
        self.assertEqual(response.redirect_chain, [(home_page.get_absolute_url(), 302)])

        invoice.refresh_from_db()
        registration.refresh_from_db()

        self.assertEqual(invoice.status, invoice.PaymentStatus.unpaid)
        self.assertEqual(invoice.outstandingBalance, s.getBasePrice())
        self.assertTrue(registration.final)


class DoorPaymentBalanceTest(DefaultSchoolTestCase):
    '''
    Staff may accept any amount at the door, and the invoice is marked as
    paid.  An amount that is more or less than the balance, or a balance that
    changed after the form was loaded, is reported to staff by email and to
    the staff member who recorded it.
    '''

    def setUp(self):
        self.gp = global_preferences_registry.manager()
        self.gp['contact__businessEmail'] = 'school@example.com'
        self.invoice = Invoice.objects.create(
            firstName='Pat', lastName='Payer', email='pat@example.com',
            grossTotal=50, total=50, status=Invoice.PaymentStatus.unpaid,
        )
        self.client.force_login(self.superuser)

    def pay(self, amount, **data):
        post_data = {
            'submissionUser': self.superuser.id,
            'invoice': str(self.invoice.id),
            'amountPaid': amount,
            'paymentMethod': ATTHEDOOR_PAYMENTMETHOD_CHOICES[0][0],
            'receivedBy': self.superuser.id,
        }
        post_data.update(data)
        response = self.client.post(reverse('doorPaymentHandler'), post_data)
        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        return [str(m) for m in get_messages(response.wsgi_request)]

    def notices(self):
        return [m for m in mail.outbox if 'did not match the balance' in m.subject]

    def test_payment_of_balance(self):
        messages = self.pay(50, expectedBalance=50)
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
        self.assertEqual(messages, [])
        self.assertEqual(self.notices(), [])

    def test_less_than_balance_is_paid_and_reported(self):
        messages = self.pay(40, expectedBalance=50)
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
        self.assertEqual(self.invoice.outstandingBalance, 10)
        self.assertTrue(
            any('still owed, but the invoice has been marked as paid' in m for m in messages),
            messages
        )
        self.assertEqual(len(self.notices()), 1)

    def test_more_than_balance_is_reported(self):
        messages = self.pay(60, expectedBalance=50)
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
        self.assertTrue(any('should be refunded' in m for m in messages), messages)
        self.assertEqual(len(self.notices()), 1)

    def test_balance_changed_after_form_was_loaded(self):
        ''' The form showed 45, and staff collected 45, but the balance is now 50. '''
        messages = self.pay(45, expectedBalance=45)
        self.assertTrue(any('changed from' in m for m in messages), messages)
        self.assertEqual(len(self.notices()), 1)

    def test_form_without_expected_balance(self):
        ''' A form loaded before this change does not send one. '''
        self.assertEqual(self.pay(50), [])
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)

    def test_form_includes_balance_shown(self):
        form = DoorPaymentForm(
            user=self.superuser.id, invoice=str(self.invoice.id), initialAmount=50,
        )
        self.assertIn('name="expectedBalance" value="50"', str(form['expectedBalance']))
