import json
from io import StringIO
from unittest import skipUnless

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from dynamic_preferences.registries import global_preferences_registry

from ..models import (
    CashPaymentRecord, EventOccurrence, Event, PublicEvent, Series, Invoice,
    InvoiceItem, Location,
    PublicEventCategory, SeriesCategory, TaxJurisdiction, TaxRule,
)
from ..constants import REG_VALIDATION_STR
from ..utils.tax import getEventTax, getItemTax, getTaxRate
from .defaults import DefaultSchoolTestCase


class TaxTestMixin(object):
    '''
    Sets up two tax jurisdictions and a location in each one.
    '''

    DEFAULT_RATE = 6.0
    SERIES_RATE = 10.0
    OTHER_RATE = 3.0

    def setUpTax(self):
        self.gp = global_preferences_registry.manager()

        # The default location is in a jurisdiction that taxes class series
        # at a different rate than everything else.
        self.jurisdiction = TaxJurisdiction.objects.create(
            name='Home Jurisdiction', defaultRate=self.DEFAULT_RATE
        )
        TaxRule.objects.create(
            jurisdiction=self.jurisdiction,
            itemType=ContentType.objects.get_for_model(Series),
            rate=self.SERIES_RATE,
        )
        self.defaultLocation.taxJurisdiction = self.jurisdiction
        self.defaultLocation.save()

        # A second location is in a jurisdiction with one rate for everything.
        self.otherJurisdiction = TaxJurisdiction.objects.create(
            name='Other Jurisdiction', defaultRate=self.OTHER_RATE
        )
        self.otherLocation = Location.objects.create(
            name='Other Location', status=Location.StatusChoices.active,
            taxJurisdiction=self.otherJurisdiction,
        )

    def tearDownTax(self):
        self.gp['registration__defaultTaxJurisdiction'] = None

    def create_public_event(self, location=None, **kwargs):
        start = timezone.now() + timedelta(days=1)
        slug = kwargs.pop('slug', 'test-tax-event')
        event = PublicEvent(
            title=kwargs.pop('title', 'Test Tax Event'), slug=slug,
            pricingTier=self.defaultPricing,
            location=location or self.defaultLocation,
            status=Event.RegStatus.enabled,
            **kwargs
        )
        event.save()
        EventOccurrence.objects.create(
            event=event, startTime=start, endTime=start + timedelta(hours=1),
        )
        event.save()
        return event


class TaxResolutionTest(TaxTestMixin, DefaultSchoolTestCase):
    '''
    Verifies the order in which tax rates are resolved: an override on the
    item, then a category rule, then a rule for the type of item, then the
    default rate of the jurisdiction, and no tax when no jurisdiction applies.
    '''

    def setUp(self):
        self.setUpTax()
        self.series = self.create_series()
        self.public_event = self.create_public_event()

    def tearDown(self):
        self.tearDownTax()

    def test_type_rule_overrides_jurisdiction_default(self):
        self.assertEqual(getEventTax(self.series), (self.SERIES_RATE, self.jurisdiction))

    def test_jurisdiction_default_applies_without_rule(self):
        self.assertEqual(
            getEventTax(self.public_event), (self.DEFAULT_RATE, self.jurisdiction)
        )

    def test_jurisdiction_follows_event_location(self):
        self.series.location = self.otherLocation
        self.assertEqual(
            getEventTax(self.series), (self.OTHER_RATE, self.otherJurisdiction)
        )

    def test_category_rule_overrides_type_rule(self):
        category = SeriesCategory.objects.create(name='Taxed Differently')
        TaxRule.objects.create(
            jurisdiction=self.jurisdiction, seriesCategory=category, rate=1.5
        )
        self.assertEqual(getEventTax(self.series)[0], self.SERIES_RATE)

        self.series.category = category
        self.assertEqual(getEventTax(self.series)[0], 1.5)

    def test_category_rule_sets_item_type(self):
        ''' A category rule always applies to the type that uses the category. '''
        category = PublicEventCategory.objects.create(name='Socials')
        rule = TaxRule.objects.create(
            jurisdiction=self.jurisdiction, publicEventCategory=category, rate=2
        )
        self.assertEqual(rule.itemType, ContentType.objects.get_for_model(PublicEvent))

        self.public_event.category = category
        self.assertEqual(getEventTax(self.public_event)[0], 2)
        # The rule does not affect class series.
        self.assertEqual(getEventTax(self.series)[0], self.SERIES_RATE)

    def test_highest_rate_applies_to_duplicate_rules(self):
        '''
        Duplicate rules are prevented by validation, but not by the database.
        If they exist anyway, the highest rate at the most specific level
        applies, regardless of the order in which the rules were created.
        '''
        series_type = ContentType.objects.get_for_model(Series)
        category = SeriesCategory.objects.create(name='Duplicated')

        # objects.create() does not call clean(), so these duplicates are saved.
        for rate in (12.0, 4.0):
            TaxRule.objects.create(
                jurisdiction=self.jurisdiction, itemType=series_type, rate=rate
            )
        # setUpTax() created a rule for class series at SERIES_RATE (10).
        self.assertEqual(getEventTax(self.series)[0], 12.0)

        for rate in (1.0, 3.0, 2.0):
            TaxRule.objects.create(
                jurisdiction=self.jurisdiction, seriesCategory=category, rate=rate
            )
        self.series.category = category
        # A category rule still prevails over a higher rule for the type.
        self.assertEqual(getEventTax(self.series)[0], 3.0)

    def test_event_override_prevails(self):
        self.series.taxRateOverride = 2.5
        self.assertEqual(getEventTax(self.series), (2.5, self.jurisdiction))

    def test_event_override_of_zero_means_exempt(self):
        self.series.taxRateOverride = 0
        self.assertEqual(getEventTax(self.series), (0, self.jurisdiction))

    def test_no_jurisdiction_means_no_tax(self):
        self.series.location = None
        self.assertEqual(getEventTax(self.series), (0, None))

    def test_default_jurisdiction_used_without_location(self):
        self.gp['registration__defaultTaxJurisdiction'] = self.otherJurisdiction
        self.series.location = None
        self.assertEqual(
            getEventTax(self.series), (self.OTHER_RATE, self.otherJurisdiction)
        )

    def test_default_jurisdiction_used_for_location_without_jurisdiction(self):
        self.gp['registration__defaultTaxJurisdiction'] = self.otherJurisdiction
        self.defaultLocation.taxJurisdiction = None
        self.defaultLocation.save()
        self.series.refresh_from_db()
        self.assertEqual(
            getEventTax(self.series), (self.OTHER_RATE, self.otherJurisdiction)
        )

    def test_item_tax_uses_passed_jurisdiction_then_default(self):
        self.assertEqual(getItemTax(None), (0, None))
        self.assertEqual(
            getItemTax(None, self.jurisdiction), (self.DEFAULT_RATE, self.jurisdiction)
        )
        self.gp['registration__defaultTaxJurisdiction'] = self.otherJurisdiction
        self.assertEqual(getItemTax(None), (self.OTHER_RATE, self.otherJurisdiction))

    def test_rate_without_jurisdiction_is_zero(self):
        self.assertEqual(getTaxRate(self.series, None), 0)

    def test_rule_validation(self):
        series_category = SeriesCategory.objects.create(name='A')
        event_category = PublicEventCategory.objects.create(name='B')

        # A rule needs either an item type or a category.
        with self.assertRaises(ValidationError):
            TaxRule(jurisdiction=self.jurisdiction, rate=1).clean()
        # A rule cannot be limited to both kinds of category.
        with self.assertRaises(ValidationError):
            TaxRule(
                jurisdiction=self.jurisdiction, seriesCategory=series_category,
                publicEventCategory=event_category, rate=1
            ).clean()
        # The category must match the item type.
        with self.assertRaises(ValidationError):
            TaxRule(
                jurisdiction=self.jurisdiction, seriesCategory=series_category,
                itemType=ContentType.objects.get_for_model(PublicEvent), rate=1
            ).clean()
        # Only one rule per jurisdiction for the same items.
        with self.assertRaises(ValidationError):
            TaxRule(
                jurisdiction=self.jurisdiction,
                itemType=ContentType.objects.get_for_model(Series), rate=1
            ).clean()


class SalesTaxCartTest(TaxTestMixin, DefaultSchoolTestCase):
    '''
    Verifies that the tax rate and jurisdiction are recorded on each invoice
    item through the CartView checkout workflow, including when one invoice
    covers events in more than one jurisdiction.
    '''

    def setUp(self):
        self.setUpTax()
        self.series = self.create_series()
        self.public_event = self.create_public_event()
        self.other_event = self.create_public_event(
            location=self.otherLocation, slug='other-tax-event',
            title='Other Tax Event',
        )

    def tearDown(self):
        self.tearDownTax()

    def _cart_checkout(self, *events):
        return self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [
                    {
                        'item_type': 'Event', 'item_id': event.id,
                        'sku': f'EVENT_{event.id}_GENERAL', 'quantity': 1
                    } for event in events
                ],
                'checkout': True,
            }),
            content_type='application/json',
        )

    def _get_invoice(self):
        invoice_id = self.client.session[REG_VALIDATION_STR].get('invoice_id')
        return Invoice.objects.get(id=invoice_id)

    def _item_for(self, invoice, event):
        return invoice.registration.eventregistration_set.get(event=event).invoiceItem

    def test_cart_series_uses_series_rule(self):
        self._cart_checkout(self.series)
        items = list(self._get_invoice().invoiceitem_set.all())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].taxRate, self.SERIES_RATE)
        self.assertEqual(items[0].taxJurisdiction, self.jurisdiction)

    def test_cart_public_event_uses_jurisdiction_default(self):
        self._cart_checkout(self.public_event)
        items = list(self._get_invoice().invoiceitem_set.all())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].taxRate, self.DEFAULT_RATE)
        self.assertEqual(items[0].taxJurisdiction, self.jurisdiction)

    def test_cart_with_events_in_two_jurisdictions(self):
        '''
        Each item on a mixed invoice carries its own rate and jurisdiction,
        and the invoice tax is the sum of the tax on its items.
        '''
        self._cart_checkout(self.series, self.public_event, self.other_event)
        invoice = self._get_invoice()

        series_item = self._item_for(invoice, self.series)
        event_item = self._item_for(invoice, self.public_event)
        other_item = self._item_for(invoice, self.other_event)

        self.assertEqual(series_item.taxRate, self.SERIES_RATE)
        self.assertEqual(series_item.taxJurisdiction, self.jurisdiction)
        self.assertEqual(event_item.taxRate, self.DEFAULT_RATE)
        self.assertEqual(event_item.taxJurisdiction, self.jurisdiction)
        self.assertEqual(other_item.taxRate, self.OTHER_RATE)
        self.assertEqual(other_item.taxJurisdiction, self.otherJurisdiction)

        for item in [series_item, event_item, other_item]:
            self.assertGreater(item.taxes, 0)
        self.assertAlmostEqual(
            invoice.taxes, series_item.taxes + event_item.taxes + other_item.taxes,
            places=4
        )

    def test_cart_exempt_event_is_not_taxed(self):
        '''
        An event with an override of 0 is exempt, even though its jurisdiction
        would otherwise tax it.
        '''
        self.public_event.taxRateOverride = 0
        self.public_event.save()
        self._cart_checkout(self.public_event)
        item = self._get_invoice().invoiceitem_set.get()
        self.assertEqual(item.taxRate, 0)
        self.assertEqual(item.taxes, 0)
        self.assertEqual(item.taxJurisdiction, self.jurisdiction)

        # Recalculating must not replace the exemption with a default rate.
        item.calculateTaxes()
        self.assertEqual(item.taxRate, 0)
        self.assertEqual(item.taxes, 0)

    def test_cart_without_jurisdiction_is_not_taxed(self):
        self.defaultLocation.taxJurisdiction = None
        self.defaultLocation.save()
        self._cart_checkout(self.series)
        item = self._get_invoice().invoiceitem_set.get()
        self.assertEqual(item.taxRate, 0)
        self.assertEqual(item.taxes, 0)
        self.assertIsNone(item.taxJurisdiction)

    def test_recorded_jurisdiction_does_not_change_with_location(self):
        ''' The jurisdiction on an invoice item is a record of the sale. '''
        self._cart_checkout(self.public_event)
        item = self._get_invoice().invoiceitem_set.get()

        self.defaultLocation.taxJurisdiction = self.otherJurisdiction
        self.defaultLocation.save()

        item = InvoiceItem.objects.get(id=item.id)
        item.calculateTaxes()
        self.assertEqual(item.taxRate, self.DEFAULT_RATE)
        self.assertEqual(item.taxJurisdiction, self.jurisdiction)

    def _assert_recalculation_matches(self, buyer_pays):
        '''
        Recalculating the invoice totals must produce the same tax for each
        item as InvoiceItem.calculateTaxes().
        '''
        self.gp['registration__buyerPaysSalesTax'] = buyer_pays
        self._cart_checkout(self.series, self.other_event)
        invoice = self._get_invoice()
        self.assertEqual(invoice.buyerPaysSalesTax, buyer_pays)

        expected = {}
        for item in invoice.invoiceitem_set.all():
            if buyer_pays:
                expected[item.id] = item.total * item.taxRate / 100
            else:
                expected[item.id] = item.total * item.taxRate / (100 + item.taxRate)
            self.assertAlmostEqual(item.taxes, expected[item.id], places=6)

        invoice.updateTotals(forceSave=True)

        for item in invoice.invoiceitem_set.all():
            self.assertAlmostEqual(item.taxes, expected[item.id], places=6)
        invoice = self._get_invoice()
        self.assertAlmostEqual(invoice.taxes, sum(expected.values()), places=6)

        # Allocating a discount recalculates the tax on the reduced prices.
        invoice.updateTotals(allocateAmounts={'total': -10})
        for item in invoice.invoiceitem_set.all():
            if buyer_pays:
                this_expected = item.total * item.taxRate / 100
            else:
                this_expected = item.total * item.taxRate / (100 + item.taxRate)
            self.assertAlmostEqual(item.taxes, this_expected, places=6)

    def test_recalculation_matches_when_buyer_pays(self):
        self._assert_recalculation_matches(True)

    def test_recalculation_matches_when_seller_pays(self):
        '''
        When the seller pays sales tax, the price includes the tax, and
        recalculating the invoice totals must not inflate it.
        '''
        try:
            self._assert_recalculation_matches(False)
        finally:
            self.gp['registration__buyerPaysSalesTax'] = True

    def _post_door_cart(self, register_id):
        self.client.login(username=self.superuser.username, password='pass')
        return self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{
                    'item_type': 'Event', 'item_id': self.series.id,
                    'sku': f'EVENT_{self.series.id}_GENERAL', 'quantity': 1
                }],
                'payAtDoor': True,
                'register_id': register_id,
                'checkout': True,
            }),
            content_type='application/json',
        )

    @skipUnless(apps.is_installed('danceschool.register'), 'register app not installed')
    def test_register_id_recorded_for_door_cart(self):
        ''' An at-the-door cart records the register that it came from. '''
        register = apps.get_model('register', 'Register').objects.create(
            title='Front Desk', slug='front-desk'
        )
        response = self._post_door_cart(register.id)
        # A successful checkout redirects to the next step of registration.
        self.assertLess(response.status_code, 400)
        self.assertEqual(self._get_invoice().data.get('register_id'), register.id)

    @skipUnless(apps.is_installed('danceschool.register'), 'register app not installed')
    def test_invalid_register_id_rejected_for_door_cart(self):
        '''
        A register that does not exist or that is disabled is rejected, rather
        than silently falling back to the default tax jurisdiction.
        '''
        Register = apps.get_model('register', 'Register')
        disabled = Register.objects.create(
            title='Closed Desk', slug='closed-desk', enabled=False
        )
        for register_id in (disabled.id, disabled.id + 1000):
            response = self._post_door_cart(register_id)
            self.assertEqual(response.status_code, 400)
            self.assertIn('register_id', response.json())

    def test_register_id_ignored_for_online_cart(self):
        '''
        The register determines the tax jurisdiction for merchandise, so an
        online customer must not be able to specify one.
        '''
        self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{
                    'item_type': 'Event', 'item_id': self.series.id,
                    'sku': f'EVENT_{self.series.id}_GENERAL', 'quantity': 1
                }],
                'register_id': 1,
                'checkout': True,
            }),
            content_type='application/json',
        )
        self.assertNotIn('register_id', self._get_invoice().data)

    def test_direct_payment_includes_tax(self):
        '''
        A registration that is marked in the session as paid directly records
        a payment of the whole balance, including the tax when the buyer pays
        it, so that nothing is left owing.
        '''
        self.gp['registration__buyerPaysSalesTax'] = True
        self._cart_checkout(self.series)
        self.client.post(reverse('getStudentInfo'), {
            'firstName': 'Direct', 'lastName': 'Payment',
            'email': 'direct@payment.com', 'agreeToPolicies': True,
        })
        invoice = self._get_invoice()
        self.assertGreater(invoice.taxes, 0)
        balance = invoice.outstandingBalance
        self.assertAlmostEqual(balance, invoice.total + invoice.taxes, places=2)

        session = self.client.session
        session[REG_VALIDATION_STR].update({
            'direct_payment': True, 'direct_payment_method': 'Cash',
        })
        session.save()
        response = self.client.get(reverse('showRegSummary'))
        self.assertTrue(response.context_data['is_complete'])

        invoice = self._get_invoice()
        payment = CashPaymentRecord.objects.get(invoice=invoice)
        self.assertAlmostEqual(payment.amount, balance, places=2)
        self.assertEqual(invoice.status, Invoice.PaymentStatus.paid)
        self.assertEqual(invoice.outstandingBalance, 0)


class TaxBackfillTest(TaxTestMixin, DefaultSchoolTestCase):
    '''
    Verifies the backfill_tax_jurisdictions management command, which applies
    the current tax rules to invoices that were created before those rules
    were in place.
    '''

    def setUp(self):
        self.setUpTax()
        self.gp['registration__buyerPaysSalesTax'] = True
        self.series = self.create_series()

        # Create an invoice at a time when no jurisdiction applied, so that
        # no tax was charged.
        self.defaultLocation.taxJurisdiction = None
        self.defaultLocation.save()
        self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{
                    'item_type': 'Event', 'item_id': self.series.id,
                    'sku': f'EVENT_{self.series.id}_GENERAL', 'quantity': 1
                }],
                'checkout': True,
            }),
            content_type='application/json',
        )
        invoice_id = self.client.session[REG_VALIDATION_STR].get('invoice_id')
        self.invoice = Invoice.objects.get(id=invoice_id)
        self.item = self.invoice.invoiceitem_set.get()
        self.price = self.item.total
        self.assertGreater(self.price, 0)
        self.assertEqual(self.item.taxes, 0)

        # The location is then assigned to its jurisdiction.
        self.defaultLocation.taxJurisdiction = self.jurisdiction
        self.defaultLocation.save()

    def tearDown(self):
        self.tearDownTax()

    def _set_status(self, status, paid=True):
        Invoice.objects.filter(id=self.invoice.id).update(
            status=status, amountPaid=self.price if paid else 0
        )

    def _run(self, *args):
        out = StringIO()
        call_command('backfill_tax_jurisdictions', *args, stdout=out)
        return out.getvalue()

    def _reload(self):
        self.invoice = Invoice.objects.get(id=self.invoice.id)
        self.item = InvoiceItem.objects.get(id=self.item.id)

    def test_dry_run_changes_nothing(self):
        self._set_status(Invoice.PaymentStatus.paid)
        for mode in ['label', 'carve-out', 'add']:
            output = self._run('--mode', mode)
            self.assertIn('dry run', output)
            self._reload()
            self.assertIsNone(self.item.taxJurisdiction)
            self.assertEqual(self.item.taxRate, 0)
            self.assertEqual(self.item.taxes, 0)
            self.assertEqual(self.item.total, self.price)

    def test_dry_run_reports_tax_due(self):
        self._set_status(Invoice.PaymentStatus.paid)
        output = self._run('--mode', 'carve-out')
        carved = self.price * self.SERIES_RATE / (100 + self.SERIES_RATE)
        added = self.price * self.SERIES_RATE / 100
        self.assertIn(self.jurisdiction.name, output)
        self.assertIn('%.2f' % carved, output)
        self.assertIn('%.2f' % added, output)

    def test_preliminary_invoices_are_ignored(self):
        self._run('--mode', 'carve-out', '--commit')
        self._reload()
        self.assertIsNone(self.item.taxJurisdiction)
        self.assertEqual(self.item.taxes, 0)

    def test_label_mode_only_records_jurisdiction(self):
        self._set_status(Invoice.PaymentStatus.paid)
        self._run('--commit')
        self._reload()
        self.assertEqual(self.item.taxJurisdiction, self.jurisdiction)
        self.assertEqual(self.item.taxRate, 0)
        self.assertEqual(self.item.taxes, 0)
        self.assertEqual(self.item.total, self.price)

    def test_carve_out_keeps_amount_collected_on_paid_invoice(self):
        self._set_status(Invoice.PaymentStatus.paid)
        old_gross = self.item.grossTotal
        self._run('--mode', 'carve-out', '--commit')
        self._reload()

        expected_total = self.price / (1 + self.SERIES_RATE / 100)

        self.assertEqual(self.item.taxJurisdiction, self.jurisdiction)
        self.assertEqual(self.item.taxRate, self.SERIES_RATE)
        self.assertAlmostEqual(self.item.total, expected_total, places=6)
        self.assertAlmostEqual(self.item.total + self.item.taxes, self.price, places=6)
        # The price before discounts moves in proportion with the price.
        self.assertAlmostEqual(
            self.item.grossTotal, old_gross * expected_total / self.price, places=6
        )
        # The original values are kept so that the change can be reversed.
        self.assertEqual(self.item.data['_tax_backfill']['total'], self.price)
        self.assertEqual(self.item.data['_tax_backfill']['taxes'], 0)

        # The invoice is still paid in full.
        self.assertEqual(self.invoice.status, Invoice.PaymentStatus.paid)
        self.assertAlmostEqual(self.invoice.total, self.item.total, places=6)
        self.assertAlmostEqual(self.invoice.taxes, self.item.taxes, places=6)
        self.assertEqual(self.invoice.outstandingBalance, 0)

    def test_carve_out_is_idempotent(self):
        self._set_status(Invoice.PaymentStatus.paid)
        self._run('--mode', 'carve-out', '--commit')
        self._reload()
        total, taxes = self.item.total, self.item.taxes

        self._run('--mode', 'carve-out', '--commit')
        self._reload()
        self.assertEqual(self.item.total, total)
        self.assertEqual(self.item.taxes, taxes)

    def test_carve_out_when_seller_pays_leaves_price_unchanged(self):
        ''' When the seller pays the tax, the price already includes it. '''
        Invoice.objects.filter(id=self.invoice.id).update(buyerPaysSalesTax=False)
        self._set_status(Invoice.PaymentStatus.paid)
        self._run('--mode', 'carve-out', '--commit')
        self._reload()

        self.assertEqual(self.item.total, self.price)
        self.assertAlmostEqual(
            self.item.taxes,
            self.price * self.SERIES_RATE / (100 + self.SERIES_RATE), places=6
        )
        self.assertAlmostEqual(self.invoice.taxes, self.item.taxes, places=6)
        self.assertEqual(self.invoice.outstandingBalance, 0)

    def test_add_mode_refuses_paid_invoices(self):
        self._set_status(Invoice.PaymentStatus.paid)
        with self.assertRaises(CommandError):
            self._run('--mode', 'add', '--commit')
        self._reload()
        self.assertIsNone(self.item.taxJurisdiction)
        self.assertEqual(self.item.taxes, 0)

        # The dry run explains what needs to happen.
        output = self._run('--mode', 'add')
        self.assertIn(str(self.invoice.id), output)
        self.assertIn('re-open', output)

    def test_add_mode_skip_paid_leaves_amounts_unchanged(self):
        self._set_status(Invoice.PaymentStatus.paid)
        self._run('--mode', 'add', '--skip-paid', '--commit')
        self._reload()
        self.assertEqual(self.item.taxJurisdiction, self.jurisdiction)
        self.assertEqual(self.item.taxes, 0)
        self.assertEqual(self.item.total, self.price)

    def test_add_mode_adds_tax_to_unpaid_invoice(self):
        self._set_status(Invoice.PaymentStatus.unpaid, paid=False)
        self._run('--mode', 'add', '--commit')
        self._reload()

        expected_tax = self.price * self.SERIES_RATE / 100
        self.assertEqual(self.item.taxJurisdiction, self.jurisdiction)
        self.assertEqual(self.item.total, self.price)
        self.assertAlmostEqual(self.item.taxes, expected_tax, places=6)
        self.assertAlmostEqual(
            self.invoice.outstandingBalance, round(self.price + expected_tax, 2), places=2
        )

    def test_jurisdiction_filter(self):
        self._set_status(Invoice.PaymentStatus.paid)
        self._run('--jurisdiction', self.otherJurisdiction.name, '--commit')
        self._reload()
        self.assertIsNone(self.item.taxJurisdiction)

        self._run('--jurisdiction', self.jurisdiction.name, '--commit')
        self._reload()
        self.assertEqual(self.item.taxJurisdiction, self.jurisdiction)
