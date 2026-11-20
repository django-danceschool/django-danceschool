from ..mixins import DiscountDetails, RegistrationAdjustmentsMixin
from ..models import Invoice, InvoiceItem
from .defaults import DefaultSchoolTestCase


class UnweightedDiscountAllocationTest(DefaultSchoolTestCase):
    '''
    A discount that does not say which items it applies to (e.g. one from
    another app) is allocated among the items in proportion to the price at
    which each is sold, not their gross (stand-alone) price.  An item that is
    sold for nothing is not reduced below zero.
    '''

    def make_invoice(self, prices, rate=10):
        '''
        A preliminary invoice with an item for each (grossTotal, total) pair.
        The first item is the parent of the others, as with a pass and the
        events that it includes.
        '''
        invoice = Invoice.objects.create(buyerPaysSalesTax=True)
        items = []
        for gross, total in prices:
            item = InvoiceItem(
                invoice=invoice, description='Item', grossTotal=gross, total=total,
                taxRate=rate, parent_item=items[0] if items else None,
            )
            if total != gross:
                item.data['_initial_total'] = total
            item.calculateTaxes()
            item.save(updateInvoiceTotals=False)
            items.append(item)
        invoice.updateTotals(save=True)
        return invoice, items

    def allocate(self, invoice, amount):
        details = DiscountDetails(
            codes=[], total_amount=amount, voucher_code=None, item_discounts={}
        )
        RegistrationAdjustmentsMixin().allocateDiscount(invoice, details, save=True)
        invoice.refresh_from_db()

    def assertTotals(self, invoice, items, expected, rate=10):
        for item, total in zip(items, expected):
            item.refresh_from_db()
            self.assertAlmostEqual(item.total, total, places=4)
            self.assertAlmostEqual(item.taxes, total * rate / 100, places=4)
        self.assertAlmostEqual(invoice.total, sum(expected), places=4)
        self.assertAlmostEqual(invoice.taxes, sum(expected) * rate / 100, places=4)

    def test_pass(self):
        '''
        A $100 pass sold as $60 for the pass and $20 for each of two
        included events, which are $50 each on their own.  A $30 discount
        is 30% off of each.
        '''
        invoice, items = self.make_invoice([(100, 60), (50, 20), (50, 20)])
        self.allocate(invoice, 30)
        self.assertTotals(invoice, items, [42, 14, 14])

    def test_pass_discount_applied_again(self):
        ''' Reloading the page (applying the discount again) gives the same result. '''
        invoice, items = self.make_invoice([(100, 60), (50, 20), (50, 20)])
        self.allocate(invoice, 30)
        self.allocate(invoice, 30)
        self.assertTotals(invoice, items, [42, 14, 14])

    def test_free_item(self):
        ''' A $20 item and a $20 item that is free: the discount is all on the first. '''
        invoice, items = self.make_invoice([(20, 20), (20, 0)])
        self.allocate(invoice, 10)
        self.assertTotals(invoice, items, [10, 0])

    def test_items_with_no_price(self):
        ''' When nothing has a price, the gross prices are used. '''
        invoice, items = self.make_invoice([(30, 0), (10, 0)])
        invoice.updateTotals(save=True, allocateAmounts={'total': 4})
        self.assertTotals(invoice, items, [3, 1])
