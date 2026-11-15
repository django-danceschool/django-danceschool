from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date

from collections import OrderedDict
from datetime import datetime, time

from danceschool.core.models import Invoice, InvoiceItem, TaxJurisdiction
from danceschool.core.utils.tax import getEventTax


# Rates and amounts are stored as floats, so they are compared with a tolerance.
TOLERANCE = 0.005


class Command(BaseCommand):
    help = (
        'Apply the current tax jurisdiction rules to existing invoice items. '
        'By default this only reports what would change; pass --commit to '
        'save changes.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode', choices=['label', 'carve-out', 'add'], default='label',
            help=(
                'label (default): record the tax jurisdiction on each item '
                'without changing any amounts. '
                'carve-out: also correct the tax on items whose tax is too low, '
                'by treating the amount that was collected as having included '
                'the tax. The price of the item is revised downward and the '
                'amount collected does not change, so paid invoices remain paid. '
                'add: also correct the tax on items whose tax is too low, by '
                'adding the tax on top of the price. This leaves a balance due, '
                'so it is only permitted for invoices that are still unpaid.'
            )
        )
        parser.add_argument(
            '--start', help='Only consider invoices created on or after this date (YYYY-MM-DD).'
        )
        parser.add_argument(
            '--end', help='Only consider invoices created on or before this date (YYYY-MM-DD).'
        )
        parser.add_argument(
            '--jurisdiction',
            help='Only consider items for this tax jurisdiction (name or ID).'
        )
        parser.add_argument(
            '--skip-paid', action='store_true',
            help=(
                'With --mode=add, skip paid invoices that would need to be '
                're-opened, and proceed with the rest.'
            )
        )
        parser.add_argument(
            '--commit', action='store_true',
            help='Save the changes. Without this option, nothing is changed.'
        )

    def get_date(self, value, name, end=False):
        if not value:
            return None
        parsed = parse_date(value)
        if not parsed:
            raise CommandError('Invalid %s date: %s. Use YYYY-MM-DD.' % (name, value))
        return timezone.make_aware(
            datetime.combine(parsed, time.max if end else time.min)
        )

    def get_jurisdiction(self, value):
        if not value:
            return None
        filters = Q(name__iexact=value)
        if value.isdigit():
            filters |= Q(id=int(value))
        jurisdiction = TaxJurisdiction.objects.filter(filters).first()
        if not jurisdiction:
            raise CommandError('No tax jurisdiction found matching "%s".' % value)
        return jurisdiction

    def resolve(self, item):
        '''
        Return (rate, jurisdiction) under the current rules for the thing that
        was sold, or None if this item is not for an event registration or
        for merchandise (e.g. a gift certificate).
        '''
        registration = getattr(item, 'eventRegistration', None)
        if registration:
            return getEventTax(registration.event)

        if apps.is_installed('danceschool.merch'):
            from danceschool.merch.models import getMerchTax

            order_item = getattr(item, 'merchorderitem', None)
            if order_item:
                return getMerchTax(order_item.item.item, item.invoice)

    def plan_item(self, item, mode):
        '''
        Determine what should happen to this item. Returns None if nothing
        applies, or a dictionary describing the item and the change.
        '''
        resolved = self.resolve(item)
        if not resolved or not resolved[1]:
            return None
        rate, jurisdiction = resolved

        invoice = item.invoice
        buyer_pays = invoice.buyerPaysSalesTax

        # The amount that was (or will be) collected for this item, with tax.
        collected = item.total + (item.taxes if buyer_pays else 0)

        # The tax that is due if the amount collected is treated as including
        # the tax, and the tax that is due if it is added on top of the price.
        due_carved = collected * rate / (100 + rate)
        due_added = (
            item.total * rate / 100 if buyer_pays else
            item.total * rate / (100 + rate)
        )

        plan = {
            'item': item,
            'rate': rate,
            'jurisdiction': jurisdiction,
            'recorded': item.taxes,
            'due_carved': due_carved,
            'due_added': due_added,
            'label': item.taxJurisdiction_id != jurisdiction.id,
            'revise': False,
            'skip': None,
        }

        due = due_added if mode == 'add' else due_carved

        if abs(item.taxRate - rate) < TOLERANCE and abs(item.taxes - due) < TOLERANCE:
            # The tax on this item is already correct.
            pass
        elif item.taxes > due + TOLERANCE:
            # Tax that was collected from a customer is never reduced
            # automatically.
            plan['skip'] = 'excess'
        elif abs(item.adjustments) > TOLERANCE:
            # The tax on refunded items needs to be reviewed by a person.
            plan['skip'] = 'refund'
        elif mode == 'add' and buyer_pays and not invoice.itemsEditable:
            plan['skip'] = 'paid'
        else:
            plan['revise'] = True

        return plan

    def apply_plan(self, plan, mode):
        '''
        Save the changes for one item. Returns False if no amounts changed,
        'added' if tax was added through the normal invoice process, or
        'direct' if the item was changed directly, in which case the totals
        of its invoice still need to be updated.
        '''
        item = plan['item']
        invoice = item.invoice
        rate = plan['rate']

        item.taxJurisdiction = plan['jurisdiction']

        if mode == 'label' or not plan['revise']:
            if plan['label']:
                InvoiceItem.objects.filter(pk=item.pk).update(
                    taxJurisdiction=plan['jurisdiction']
                )
                revenue_item = getattr(item, 'revenueitem', None)
                if revenue_item:
                    type(revenue_item).objects.filter(pk=revenue_item.pk).update(
                        taxJurisdiction=plan['jurisdiction']
                    )
            return False

        # Keep a record of the original values so that the change can be
        # reviewed or reversed later.
        item.data['_tax_backfill'] = {
            'date': timezone.now().isoformat(),
            'mode': mode,
            'grossTotal': item.grossTotal,
            'total': item.total,
            'taxes': item.taxes,
            'taxRate': item.taxRate,
        }

        if mode == 'add' and invoice.buyerPaysSalesTax:
            # Tax is added on top of the existing price, and the invoice
            # totals (including the balance due) are updated accordingly.
            item.taxRate = rate
            item.calculateTaxes()
            item.save()
            return 'added'

        if invoice.buyerPaysSalesTax:
            # The amount collected is treated as having included the tax, so
            # the price is revised downward. The price before discounts is
            # revised in the same proportion.
            collected = item.total + item.taxes
            new_total = collected / (1 + (rate / 100))
            ratio = (new_total / item.total) if item.total else 1
            item.grossTotal = item.grossTotal * ratio
            if '_initial_total' in item.data:
                item.data['_initial_total'] = item.data['_initial_total'] * ratio
            item.total = new_total
            item.taxes = new_total * (rate / 100)
        else:
            # The seller pays the tax, so the price already includes it.
            item.taxes = plan['due_carved']
        item.taxRate = rate

        # The invoice totals are set directly below, because the amount
        # collected has not changed and the invoice may already be paid.
        item.save(restrictStatus=False, updateInvoiceTotals=False)
        return 'direct'

    def update_invoice_totals(self, invoice):
        totals = invoice.invoiceitem_set.aggregate(
            grossTotal=Sum('grossTotal'), total=Sum('total'), taxes=Sum('taxes'),
        )
        Invoice.objects.filter(pk=invoice.pk).update(
            **{k: v or 0 for k, v in totals.items()}
        )

    def handle(self, *args, **options):
        mode = options['mode']
        commit = options['commit']
        start = self.get_date(options.get('start'), 'start')
        end = self.get_date(options.get('end'), 'end', end=True)
        only_jurisdiction = self.get_jurisdiction(options.get('jurisdiction'))

        if not TaxJurisdiction.objects.exists():
            raise CommandError(
                'No tax jurisdictions have been defined, so there is nothing to apply.'
            )

        # Preliminary invoices are repriced at checkout. Invoices that were
        # cancelled, refunded in full, or never successfully processed have
        # no tax to account for.
        items = InvoiceItem.objects.exclude(invoice__status__in=[
            Invoice.PaymentStatus.preliminary, Invoice.PaymentStatus.cancelled,
            Invoice.PaymentStatus.fullRefund, Invoice.PaymentStatus.rejected,
            Invoice.PaymentStatus.error,
        ]).order_by('invoice__creationDate', 'id')

        # Load what is examined for every item along with the item. The event
        # is deliberately not included: select_related() would return it as a
        # plain Event rather than as a Series or PublicEvent, and its category
        # would then not be available to the tax rules.
        related = ['invoice', 'taxJurisdiction', 'eventRegistration']
        if apps.is_installed('danceschool.financial'):
            related.append('revenueitem')
        if apps.is_installed('danceschool.merch'):
            related.append('merchorderitem__item__item')
        items = items.select_related(*related)

        if start:
            items = items.filter(invoice__creationDate__gte=start)
        if end:
            items = items.filter(invoice__creationDate__lte=end)

        plans = []
        for item in items:
            plan = self.plan_item(item, mode)
            if not plan:
                continue
            if only_jurisdiction and plan['jurisdiction'].id != only_jurisdiction.id:
                continue
            if plan['label'] or plan['revise'] or plan['skip']:
                plans.append(plan)

        self.report(plans, mode)

        blocked = [x for x in plans if x['skip'] == 'paid']
        if blocked and mode == 'add' and not options['skip_paid']:
            invoice_ids = list(OrderedDict.fromkeys(
                str(x['item'].invoice_id) for x in blocked
            ))
            self.stdout.write(self.style.ERROR(
                '\n%s paid invoice(s) cannot have tax added to them, because '
                'doing so would leave a balance due. Either re-open these '
                'invoices yourself and run this command again, use '
                '--mode=carve-out to keep the amount collected the same, or '
                'pass --skip-paid to proceed with the other invoices:' %
                len(invoice_ids)
            ))
            for invoice_id in invoice_ids:
                self.stdout.write('  %s' % invoice_id)
            if commit:
                raise CommandError('No changes were made.')

        if not commit:
            self.stdout.write(self.style.WARNING(
                '\nThis was a dry run and nothing has been changed. '
                'Run again with --commit to save these changes.'
            ))
            return

        num_labelled = 0
        num_revised = 0
        with transaction.atomic():
            invoices = OrderedDict()
            for plan in plans:
                result = self.apply_plan(plan, mode)
                if result:
                    num_revised += 1
                    if result == 'direct':
                        invoices[plan['item'].invoice_id] = plan['item'].invoice
                elif plan['label']:
                    num_labelled += 1
            for invoice in invoices.values():
                self.update_invoice_totals(invoice)

        self.stdout.write(self.style.SUCCESS(
            '\nChanges saved. %s item(s) had their tax corrected, and %s more '
            'had only their tax jurisdiction recorded.' % (num_revised, num_labelled)
        ))

    def report(self, plans, mode):
        ''' Summarize what would be changed, by jurisdiction and month. '''
        rows = OrderedDict()
        for plan in plans:
            item = plan['item']
            key = (plan['jurisdiction'].name, item.invoice.creationDate.strftime('%Y-%m'))
            row = rows.setdefault(key, {
                'invoices': set(), 'items': 0, 'label': 0, 'revise': 0,
                'recorded': 0, 'due_carved': 0, 'due_added': 0,
            })
            row['invoices'].add(item.invoice_id)
            row['items'] += 1
            row['label'] += int(plan['label'])
            # Only items whose tax is too low count toward the tax shortfall.
            if plan['skip'] != 'excess':
                wrong = (
                    abs(item.taxes - plan['due_carved']) > TOLERANCE or
                    abs(item.taxRate - plan['rate']) > TOLERANCE
                )
                row['revise'] += int(wrong)
                if wrong:
                    row['recorded'] += plan['recorded']
                    row['due_carved'] += plan['due_carved']
                    row['due_added'] += plan['due_added']

        self.stdout.write('Mode: %s\n' % mode)
        header = (
            'Jurisdiction', 'Month', 'Invoices', 'Items', 'To label',
            'Tax wrong', 'Recorded', 'Due (carved out)', 'Due (added)',
        )
        template = '%-24s %-8s %8s %6s %8s %9s %10s %17s %12s'
        self.stdout.write(template % header)

        totals = {
            'invoices': set(), 'items': 0, 'label': 0, 'revise': 0,
            'recorded': 0, 'due_carved': 0, 'due_added': 0,
        }
        for (jurisdiction, month), row in sorted(rows.items()):
            self.stdout.write(template % (
                jurisdiction[:24], month, len(row['invoices']), row['items'],
                row['label'], row['revise'], '%.2f' % row['recorded'],
                '%.2f' % row['due_carved'], '%.2f' % row['due_added'],
            ))
            totals['invoices'] |= row['invoices']
            for key in ['items', 'label', 'revise', 'recorded', 'due_carved', 'due_added']:
                totals[key] += row[key]
        self.stdout.write(template % (
            'TOTAL', '', len(totals['invoices']), totals['items'], totals['label'],
            totals['revise'], '%.2f' % totals['recorded'],
            '%.2f' % totals['due_carved'], '%.2f' % totals['due_added'],
        ))

        self.stdout.write(
            '\n"Tax wrong" counts the items whose recorded tax is lower than '
            'the tax that is due under the current rules. For those items:'
        )
        self.stdout.write(
            '  Additional tax owed if it is carved out of what was collected: %.2f' %
            (totals['due_carved'] - totals['recorded'])
        )
        self.stdout.write(
            '  Additional tax to collect from customers if it is added on top:  %.2f' %
            (totals['due_added'] - totals['recorded'])
        )

        skipped = {
            'excess': 'item(s) have more tax recorded than is due, and need to be reviewed by hand',
            'refund': 'item(s) with incorrect tax have refunds or adjustments, and need to be reviewed by hand',
            'paid': 'item(s) are on paid invoices that cannot have tax added to them',
        }
        for key, message in skipped.items():
            count = len([x for x in plans if x['skip'] == key])
            if count:
                self.stdout.write(self.style.WARNING('  %s %s.' % (count, message)))

        if mode == 'label':
            self.stdout.write(
                '\nIn this mode, only the tax jurisdiction is recorded on the %s '
                'item(s) to label. No amounts are changed.' % totals['label']
            )
