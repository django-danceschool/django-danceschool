from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.urls import reverse

from ..constants import REFUND_VALIDATION_STR
from ..models import EventRegistration, Invoice, InvoiceItem, Registration
from .defaults import DefaultSchoolTestCase


class FakePayment(object):
    '''
    A refundable payment that refunds whatever it is asked to, up to the
    amount that remains of it, and records each amount that it was asked for.
    A list of amounts passed as fail_after makes it fail once that many
    refunds have been made.
    '''

    refundable = True
    methodName = 'Fake'

    def __init__(self, recordId='P1', amount=1000, fail_after=None):
        self.recordId = recordId
        self.remaining = amount
        self.fail_after = fail_after
        self.requested = []

    @property
    def netAmountPaid(self):
        return self.remaining

    def refund(self, amount):
        if self.fail_after is not None and len(self.requested) >= self.fail_after:
            return [{'status': 'error', 'errors': [{'message': 'Declined'}]}]
        self.requested.append(amount)
        self.remaining -= amount
        return [{'status': 'success', 'refundAmount': amount, 'fees': 0}]


class PaymentList(list):
    ''' Stands in for the queryset of payments that get_payments() returns. '''

    def first(self):
        return self[0] if self else None


class RefundTestBase(DefaultSchoolTestCase):
    '''
    Refunds are submitted through the refund form, as staff would, so that the
    amounts that the form starts with (the refunds already made) are tested
    as well.
    '''

    def setUp(self):
        self.client.force_login(self.superuser)
        self.payments = [FakePayment()]
        patcher = mock.patch.object(
            Invoice, 'get_payments', lambda invoice: PaymentList(self.payments)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_invoice(self, prices=(100,), rate=10, buyer_pays=True, adjustments=0, rates=None):
        '''
        A paid invoice with an item for each price, each taxed at the passed
        rate (or at the rate in the same position of rates).  Adjustments
        (e.g. a post-tax gift certificate) are made to the first item before
        it is paid.
        '''
        invoice = Invoice.objects.create(
            status=Invoice.PaymentStatus.unpaid, buyerPaysSalesTax=buyer_pays,
        )
        items = []
        for n, price in enumerate(prices):
            item = InvoiceItem(
                invoice=invoice, description='Item %s' % n,
                grossTotal=price, total=price,
                taxRate=rates[n] if rates else rate,
                adjustments=adjustments if n == 0 else 0,
            )
            item.calculateTaxes()
            item.save()
            items.append(item)
        invoice.updateTotals(save=True)
        invoice.processPayment(amount=invoice.outstandingBalance, fees=0)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.PaymentStatus.paid)
        return invoice, items

    def refund(self, invoice, amounts):
        '''
        Submit the refund form with the passed refund (the total refunded so
        far, as the form asks for it) for each item, and confirm it.
        '''
        response = self.client.get(reverse('refundProcessing', args=(invoice.id,)))
        form = response.context_data['form']
        data = {
            'id': str(invoice.id),
            'initial_refund_amount': form.fields['initial_refund_amount'].initial,
            'total_refund_amount': sum(amounts.values()),
            'comments': '',
        }
        for item in invoice.invoiceitem_set.all():
            data['item_refundamount_%s' % item.id] = amounts.get(
                item, form.fields['item_refundamount_%s' % item.id].initial
            )
        response = self.client.post(reverse('refundProcessing', args=(invoice.id,)), data)
        self.assertRedirects(response, reverse('refundConfirmation'), fetch_redirect_response=False)
        self.client.get(reverse('refundConfirmation') + '?confirmed=true')
        self.assertNotIn(REFUND_VALIDATION_STR, self.client.session)
        invoice.refresh_from_db()
        for item in invoice.invoiceitem_set.all():
            item.refresh_from_db()
        return invoice


class RefundRecordingTest(RefundTestBase):
    '''
    A refund is recorded in the refunds of each invoice item and of the
    invoice, separately from discounts, vouchers and other adjustments, and
    each refund is recorded once.
    '''

    def test_refund_is_recorded_as_a_refund(self):
        invoice, (item,) = self.make_invoice()
        invoice = self.refund(invoice, {item: 30})

        item.refresh_from_db()
        self.assertEqual(self.payments[0].requested, [30])
        self.assertAlmostEqual(item.refunds, 30)
        self.assertAlmostEqual(item.adjustments, 0)
        self.assertAlmostEqual(invoice.refunds, 30)
        self.assertAlmostEqual(invoice.adjustments, 0)
        self.assertAlmostEqual(invoice.amountPaid, 80)
        self.assertAlmostEqual(invoice.outstandingBalance, 0)
        self.assertEqual(invoice.status, Invoice.PaymentStatus.paid)

    def test_second_refund_is_not_counted_twice(self):
        '''
        The refund form asks for the total refunded so far.  Raising it from
        $30 to $50 refunds another $20, and records $50 in all.
        '''
        invoice, (item,) = self.make_invoice()
        self.refund(invoice, {item: 30})
        invoice = self.refund(invoice, {item: 50})

        item.refresh_from_db()
        self.assertEqual(self.payments[0].requested, [30, 20])
        self.assertAlmostEqual(item.refunds, 50)
        self.assertAlmostEqual(invoice.refunds, 50)
        self.assertAlmostEqual(invoice.amountPaid, 60)
        self.assertAlmostEqual(invoice.outstandingBalance, 0)

    def test_second_refund_goes_to_the_item_it_is_for(self):
        invoice, (item_a, item_b) = self.make_invoice(prices=(100, 50))
        self.refund(invoice, {item_a: 20})
        invoice = self.refund(invoice, {item_a: 20, item_b: 10})

        item_a.refresh_from_db()
        item_b.refresh_from_db()
        self.assertAlmostEqual(item_a.refunds, 20)
        self.assertAlmostEqual(item_b.refunds, 10)
        self.assertAlmostEqual(invoice.refunds, 30)

    def test_credit_is_not_counted_as_a_refund(self):
        '''
        A $20 post-tax credit (e.g. a gift certificate) is not a refund, so
        the form starts with nothing refunded, and a $30 refund asks the
        payment processor for $30.
        '''
        invoice, (item,) = self.make_invoice(adjustments=-20)
        self.assertAlmostEqual(invoice.amountPaid, 90)

        response = self.client.get(reverse('refundProcessing', args=(invoice.id,)))
        form = response.context_data['form']
        self.assertEqual(form.fields['initial_refund_amount'].initial, 0)
        self.assertEqual(form.fields['item_refundamount_%s' % item.id].initial, 0)

        invoice = self.refund(invoice, {item: 30})
        item.refresh_from_db()
        self.assertEqual(self.payments[0].requested, [30])
        self.assertAlmostEqual(item.refunds, 30)
        self.assertAlmostEqual(item.adjustments, -20)
        self.assertAlmostEqual(invoice.amountPaid, 60)
        self.assertAlmostEqual(invoice.outstandingBalance, 0)

    def test_full_refund(self):
        invoice, (item,) = self.make_invoice(adjustments=-20)
        invoice = self.refund(invoice, {item: 90})
        self.assertEqual(invoice.status, Invoice.PaymentStatus.fullRefund)
        self.assertAlmostEqual(invoice.amountPaid, 0)
        self.assertAlmostEqual(invoice.outstandingBalance, 0)

    def test_failed_refund_records_only_what_succeeded(self):
        '''
        When the second of two payments cannot be refunded, only the refund
        of the first is recorded, and it can be completed later.
        '''
        self.payments = [
            FakePayment('P1', amount=30), FakePayment('P2', amount=80, fail_after=0)
        ]
        invoice, (item,) = self.make_invoice()
        invoice = self.refund(invoice, {item: 50})

        item.refresh_from_db()
        self.assertAlmostEqual(item.refunds, 30)
        self.assertAlmostEqual(invoice.refunds, 30)
        self.assertAlmostEqual(invoice.amountPaid, 80)
        self.assertEqual(invoice.data['refunds'][-1]['status'], 'error')

        self.payments[1].fail_after = None
        invoice = self.refund(invoice, {item: 50})
        item.refresh_from_db()
        self.assertEqual(self.payments[1].requested, [20])
        self.assertAlmostEqual(item.refunds, 50)
        self.assertAlmostEqual(invoice.amountPaid, 60)

    def test_refunds_are_kept_when_totals_are_updated(self):
        ''' e.g. when the payment processor's fees are recorded later. '''
        invoice, (item,) = self.make_invoice()
        invoice = self.refund(invoice, {item: 30})
        invoice.updateTotals(forceSave=True, allocateAmounts={'fees': 2})

        item.refresh_from_db()
        invoice.refresh_from_db()
        self.assertAlmostEqual(item.refunds, 30)
        self.assertAlmostEqual(item.fees, 2)
        self.assertAlmostEqual(invoice.refunds, 30)


class RefundTaxTest(RefundTestBase):
    '''
    The tax on a $100 item taxed at 10% is the same fraction of each dollar
    that is paid for it, so the same fraction of a refund is tax that is
    refunded.  It is no longer owed, and it is not subtracted from revenue.
    '''

    def assertRefund(self, item, refunded_taxes, net):
        item = InvoiceItem.objects.get(id=item.id)
        self.assertAlmostEqual(item.refundedTaxes, refunded_taxes, places=4)
        self.assertAlmostEqual(item.netRevenue, net, places=4)
        self.assertAlmostEqual(item.net, net, places=4)

        revenue = item.revenueitem.__class__.objects.get(id=item.revenueitem.id)
        self.assertAlmostEqual(revenue.refunds, item.refunds, places=4)
        self.assertAlmostEqual(revenue.refundedTaxes, refunded_taxes, places=4)
        self.assertAlmostEqual(revenue.netRevenue, net, places=4)
        self.assertAlmostEqual(revenue.net, net, places=4)

        invoice = Invoice.objects.get(id=item.invoice.id)
        self.assertAlmostEqual(invoice.refundedTaxes, refunded_taxes, places=4)
        self.assertAlmostEqual(invoice.netRevenue, net, places=4)

    def test_full_refund_when_buyer_pays_tax(self):
        invoice, (item,) = self.make_invoice(buyer_pays=True)
        self.refund(invoice, {item: 110})
        item.refresh_from_db()
        # The tax on the sale is unchanged; the refunded tax is worked out.
        self.assertAlmostEqual(item.taxes, 10)
        self.assertRefund(item, refunded_taxes=10, net=0)

    def test_full_refund_when_seller_pays_tax(self):
        invoice, (item,) = self.make_invoice(buyer_pays=False)
        self.refund(invoice, {item: 100})
        self.assertRefund(item, refunded_taxes=100 * 0.1 / 1.1, net=0)

    def test_partial_refund_when_buyer_pays_tax(self):
        ''' $55 of the $110 paid is refunded, so $5 of tax is refunded. '''
        invoice, (item,) = self.make_invoice(buyer_pays=True)
        self.refund(invoice, {item: 55})
        self.assertRefund(item, refunded_taxes=5, net=50)

    def test_partial_refund_when_seller_pays_tax(self):
        invoice, (item,) = self.make_invoice(buyer_pays=False)
        self.refund(invoice, {item: 55})
        net = (100 - 55) / 1.1
        self.assertRefund(item, refunded_taxes=55 * 0.1 / 1.1, net=net)

    def test_items_taxed_at_different_rates(self):
        '''
        The refunded tax on an invoice is the sum over its items, so a refund
        of only one item uses that item's rate.
        '''
        invoice, (item_a, item_b) = self.make_invoice(prices=(100, 100), rates=(10, 0))
        self.refund(invoice, {item_a: 0, item_b: 100})
        invoice = Invoice.objects.get(id=invoice.id)
        self.assertAlmostEqual(invoice.refundedTaxes, 0, places=4)
        self.assertAlmostEqual(invoice.netRevenue, 100, places=4)

    def test_untaxed_item(self):
        invoice, (item,) = self.make_invoice(rate=0)
        self.refund(invoice, {item: 40})
        self.assertRefund(item, refunded_taxes=0, net=60)


class PassRefundTest(RefundTestBase):
    '''
    The price of a pass is allocated among the pass and the events that it
    includes, each of which has its own registration.  When the pass is
    refunded in full, the registrations for the included events are
    cancelled as well, even when none of the price was allocated to them.
    '''

    def make_pass_invoice(self, allocations):
        '''
        A paid, untaxed invoice for a pass, with the passed totals for the
        pass and for each event that it includes.
        '''
        invoice = Invoice.objects.create(buyerPaysSalesTax=True)
        registration = Registration.objects.create(invoice=invoice, final=True)
        parent = EventRegistration(registration=registration, event=self.create_series())
        parent.save(grossTotal=allocations[0], total=allocations[0])
        registrations = [parent]
        for total in allocations[1:]:
            er = EventRegistration(registration=registration, event=self.create_series())
            er.save(grossTotal=50, total=total, parent_id=parent.id)
            registrations.append(er)
        invoice.status = Invoice.PaymentStatus.unpaid
        invoice.updateTotals(save=True)
        invoice.processPayment(amount=invoice.outstandingBalance, fees=0)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.PaymentStatus.paid)
        return invoice, registrations

    def assertCancelled(self, registrations, expected):
        self.assertEqual(
            [EventRegistration.objects.get(id=x.id).cancelled for x in registrations],
            expected
        )

    def test_full_refund_of_pass(self):
        invoice, ers = self.make_pass_invoice([60, 20, 20])
        self.refund(invoice, {x.invoiceItem: x.invoiceItem.total for x in ers})
        self.assertEqual(invoice.status, Invoice.PaymentStatus.fullRefund)
        self.assertCancelled(ers, [True, True, True])

    def test_full_refund_of_pass_with_unpriced_included_events(self):
        invoice, ers = self.make_pass_invoice([100, 0, 0])
        self.refund(invoice, {ers[0].invoiceItem: 100})
        self.assertEqual(invoice.status, Invoice.PaymentStatus.fullRefund)
        self.assertCancelled(ers, [True, True, True])

    def test_partial_refund_of_pass(self):
        invoice, ers = self.make_pass_invoice([60, 20, 20])
        self.refund(invoice, {ers[0].invoiceItem: 30})
        self.assertCancelled(ers, [False, False, False])

    def test_included_event_still_paid_for(self):
        '''
        An included event that still has an amount paid for it is not
        cancelled when only the pass is refunded.
        '''
        invoice, ers = self.make_pass_invoice([60, 20, 0])
        self.refund(invoice, {ers[0].invoiceItem: 60})
        self.assertCancelled(ers, [True, False, True])


class CheckRefundsCommandTest(RefundTestBase):
    '''
    Before refunds were recorded separately, they were recorded in the
    adjustments of each invoice item (sometimes more than once).  The
    check_refunds command lists each invoice whose refunds do not match the
    refunds recorded by the payment processors, so that it can be reviewed.
    '''

    def legacy_invoice(self, refunds, adjustments):
        invoice, (item,) = self.make_invoice()
        invoice.data['refunds'] = [
            {'status': 'success', 'refundAmount': x, 'fees': 0, 'id': 'P1'}
            for x in refunds
        ]
        invoice.save()
        item.adjustments = adjustments
        item.save(restrictStatus=False)
        invoice.refresh_from_db()
        return invoice

    def run_command(self):
        out = StringIO()
        call_command('check_refunds', stdout=out)
        return out.getvalue()

    def test_lists_refunds_recorded_as_adjustments(self):
        legacy = self.legacy_invoice([30], adjustments=-30)
        double = self.legacy_invoice([30, 20], adjustments=-80)

        current, (item,) = self.make_invoice()
        self.refund(current, {item: 30})
        credit, _items = self.make_invoice(adjustments=-20)

        output = self.run_command()
        self.assertIn(str(legacy.id), output)
        self.assertIn(str(double.id), output)
        self.assertNotIn(str(current.id), output)
        self.assertNotIn(str(credit.id), output)

        # The adjustments that the recorded refunds do not explain.
        double_line = next(x for x in output.splitlines() if str(double.id) in x)
        self.assertIn('-30.00', double_line)

    def test_nothing_to_report(self):
        current, (item,) = self.make_invoice()
        self.refund(current, {item: 30})
        self.assertIn('No invoices', self.run_command())
