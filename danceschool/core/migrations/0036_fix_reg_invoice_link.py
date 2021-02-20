from django.conf import settings
from django.db import migrations


def fix_reg_invoice_link(apps, schema_editor):
    '''
    Take the JSON data field in Registrations and EventRegistrations and use it
    to populate the Invoice/InvoiceItem fields
    '''
    Registration = apps.get_model("core", "Registration")
    EventRegistration = apps.get_model("core", "EventRegistration")
    Invoice = apps.get_model("core", "Invoice")
    InvoiceItem = apps.get_model("core", "InvoiceItem")
    db_alias = schema_editor.connection.alias

    to_update = Registration.objects.using(db_alias).filter(
        invoice__isnull=True, data__isnull=False
    )

    for x in to_update:
        invoice_id = x.data.pop('0034__invoice__id', None)
        if invoice_id:
            x.invoice = Invoice.objects.get(id=invoice_id)
            x.save()

    to_update_eventreg = EventRegistration.objects.using(db_alias).filter(
        invoiceItem__isnull=True, data__isnull=False
    )

    for x in to_update_eventreg:
        item_id = x.data.pop('0034__invoiceitem__id', None)
        if item_id:
            x.invoiceItem = InvoiceItem.objects.get(id=item_id)
            x.save()


def reverse_reg_invoice_link(apps, schema_editor):
    '''
    Note that this migration reversal does not actually break the linkages to
    invoices, it just puts the ID back into the appropriate JSON field so that
    the overall linkage can be reversed.
    '''
    Registration = apps.get_model("core", "Registration")
    EventRegistration = apps.get_model("core", "EventRegistration")
    db_alias = schema_editor.connection.alias

    to_update = Registration.objects.using(db_alias).filter(
        invoice__isnull=False
    )

    for x in to_update:
        x.data.update({'0034__invoice__id': x.invoice.id})
        x.save()

    to_update_eventreg = EventRegistration.objects.using(db_alias).filter(
        invoiceItem__isnull=False
    )

    for x in to_update_eventreg:
        x.data.update({'0034__invoiceitem__id': x.invoiceItem.id})
        x.save()


def set_reg_final(apps, schema_editor):
    '''
    Registrations that have a null value for final status are set to final.
    Note that the revese of this migration does not do anything.
    '''
    Registration = apps.get_model("core", "Registration")
    db_alias = schema_editor.connection.alias

    Registration.objects.using(db_alias).filter(final__isnull=True).update(
        final=True
    )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0035_auto_20210127_2052'),
    ]

    operations = [
        migrations.RunPython(fix_reg_invoice_link, reverse_reg_invoice_link),
        migrations.RunPython(set_reg_final, migrations.RunPython.noop),
    ]
