import json

from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from dynamic_preferences.registries import global_preferences_registry

from ..models import EventOccurrence, Event, PublicEvent, Invoice
from ..constants import REG_VALIDATION_STR
from .defaults import DefaultSchoolTestCase


class SalesTaxDifferentiationTest(DefaultSchoolTestCase):
    '''
    Verifies that SeriesSalesTaxRate and PublicEventSalesTaxRate are applied
    independently to class series and public event registrations, respectively,
    through the CartView checkout workflow.
    '''

    SERIES_TAX_RATE = 10.0
    EVENT_TAX_RATE = 5.0

    def setUp(self):
        self.gp = global_preferences_registry.manager()
        self.gp['registration__seriesSalesTaxRate'] = self.SERIES_TAX_RATE
        self.gp['registration__publicEventSalesTaxRate'] = self.EVENT_TAX_RATE

        self.series = self.create_series()

        start = timezone.now() + timedelta(days=1)
        self.public_event = PublicEvent(
            title='Test Tax Event',
            slug='test-tax-event',
            pricingTier=self.defaultPricing,
            location=self.defaultLocation,
            status=Event.RegStatus.enabled,
        )
        self.public_event.save()
        EventOccurrence.objects.create(
            event=self.public_event,
            startTime=start,
            endTime=start + timedelta(hours=1),
        )
        self.public_event.save()

    def tearDown(self):
        self.gp['registration__seriesSalesTaxRate'] = 0.0
        self.gp['registration__publicEventSalesTaxRate'] = 0.0

    # --- CartView workflow ---

    def _cart_checkout(self, event):
        sku = f'EVENT_{event.id}_GENERAL'
        return self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [{'item_type': 'Event', 'item_id': event.id,
                           'sku': sku, 'quantity': 1}],
                'checkout': True,
            }),
            content_type='application/json',
        )

    def _get_invoice_items(self):
        invoice_id = self.client.session[REG_VALIDATION_STR].get('invoice_id')
        invoice = Invoice.objects.get(id=invoice_id)
        return list(invoice.invoiceitem_set.all())

    def test_cart_series_uses_series_tax_rate(self):
        '''CartView checkout for a Series applies seriesSalesTaxRate.'''
        self._cart_checkout(self.series)
        items = self._get_invoice_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].taxRate, self.SERIES_TAX_RATE)

    def test_cart_public_event_uses_public_event_tax_rate(self):
        '''CartView checkout for a PublicEvent applies publicEventSalesTaxRate.'''
        self._cart_checkout(self.public_event)
        items = self._get_invoice_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].taxRate, self.EVENT_TAX_RATE)

    def test_cart_series_and_public_event_get_different_rates(self):
        '''
        When both a Series and a PublicEvent are in the cart, their invoice
        items carry different tax rates matching each type's preference.
        '''
        series_sku = f'EVENT_{self.series.id}_GENERAL'
        event_sku = f'EVENT_{self.public_event.id}_GENERAL'
        self.client.post(
            reverse('cart'),
            data=json.dumps({
                'items': [
                    {'item_type': 'Event', 'item_id': self.series.id,
                     'sku': series_sku, 'quantity': 1},
                    {'item_type': 'Event', 'item_id': self.public_event.id,
                     'sku': event_sku, 'quantity': 1},
                ],
                'checkout': True,
            }),
            content_type='application/json',
        )
        invoice_id = self.client.session[REG_VALIDATION_STR].get('invoice_id')
        invoice = Invoice.objects.get(id=invoice_id)

        series_regs = invoice.registration.eventregistration_set.filter(event=self.series)
        event_regs = invoice.registration.eventregistration_set.filter(event=self.public_event)
        self.assertTrue(series_regs.exists())
        self.assertTrue(event_regs.exists())

        series_item = series_regs.first().invoiceItem
        event_item = event_regs.first().invoiceItem
        self.assertEqual(series_item.taxRate, self.SERIES_TAX_RATE)
        self.assertEqual(event_item.taxRate, self.EVENT_TAX_RATE)
