from django.apps import apps
from django.core.management.base import BaseCommand
from django.db.models import Q

from danceschool.core.models import Invoice


TOLERANCE = 0.01


class Command(BaseCommand):
    help = (
        'List the invoices whose recorded refunds do not match the refunds '
        'that were made through the refund form or reported by a payment '
        'processor.  Refunds made before refunds were recorded separately are '
        'included in the adjustments of an invoice (and could be counted more '
        'than once), and the tax on them was not treated as refunded, so these '
        'invoices should be reviewed.  Nothing is changed.'
    )

    def recordedRefunds(self, invoice):
        ''' The refunds that are listed on the invoice as successful. '''
        return sum([
            float(x.get('refundAmount') or 0)
            for x in (invoice.data or {}).get('refunds', [])
            if x.get('status') == 'success'
        ])

    def postTaxVouchers(self, invoice):
        ''' Post-tax vouchers (e.g. gift certificates) are also adjustments. '''
        if not apps.is_installed('danceschool.vouchers'):
            return 0
        from danceschool.vouchers.models import VoucherUse
        return sum(VoucherUse.objects.filter(
            invoice=invoice, beforeTax=False, applied=True,
        ).values_list('amount', flat=True))

    def handle(self, *args, **options):
        invoices = Invoice.objects.filter(
            Q(refunds__gt=0) | Q(data__has_key='refunds') |
            Q(status=Invoice.PaymentStatus.fullRefund)
        ).order_by('modifiedDate')

        rows = []
        for invoice in invoices:
            recorded = self.recordedRefunds(invoice)
            if abs(recorded - invoice.refunds) < TOLERANCE:
                continue

            # The refunds that are not in the refunds of the invoice are
            # expected to be in its adjustments (as negative amounts), along
            # with any post-tax vouchers.  Whatever else is in the adjustments
            # is not explained by either (e.g. a refund that was counted more
            # than once, or a credit entered by staff).
            legacy = recorded - invoice.refunds
            unexplained = invoice.adjustments + legacy + self.postTaxVouchers(invoice)

            if invoice.refunds < TOLERANCE:
                reason = 'refunds are in adjustments'
            else:
                reason = 'refunds do not match'
            rows.append((invoice, recorded, unexplained, reason))

        if not rows:
            self.stdout.write('No invoices were found whose refunds need to be reviewed.')
            return

        self.stdout.write(
            'Invoices whose refunds need to be reviewed.  "Recorded" is the total '
            'of the successful refunds listed on the invoice.  "Unexplained" is '
            'the part of the adjustments that is not explained by those refunds '
            'or by post-tax vouchers (0.00 means that the adjustments match).'
        )
        header = '%-36s  %-10s  %-6s  %10s  %10s  %12s  %12s  %s' % (
            'Invoice', 'Modified', 'Status', 'Recorded', 'Refunds',
            'Adjustments', 'Unexplained', 'Issue',
        )
        self.stdout.write(header)
        self.stdout.write('-' * len(header))
        for invoice, recorded, unexplained, reason in rows:
            self.stdout.write('%-36s  %-10s  %-6s  %10.2f  %10.2f  %12.2f  %12.2f  %s' % (
                invoice.id, invoice.modifiedDate.strftime('%Y-%m-%d'),
                invoice.status, recorded, invoice.refunds, invoice.adjustments,
                unexplained, reason,
            ))
        self.stdout.write('%s invoice(s) found.' % len(rows))
