from django.conf import settings
from django.db import migrations


def update_reg_data(apps, schema_editor):
    '''
    Populate JSON data field with the id of the Invoice/InvoiceItem associated
    with each Registration/EventRegistration so that the foreign key can be
    moved from the Invoice models to the Registration models.
    '''
    Registration = apps.get_model("core", "Registration")
    EventRegistration = apps.get_model("core", "EventRegistration")
    Invoice = apps.get_model("core", "Invoice")
    InvoiceItem = apps.get_model("core", "InvoiceItem")
    db_alias = schema_editor.connection.alias

    to_update = Invoice.objects.filter(finalRegistration__isnull=False).values(
        'id', 'finalRegistration'
    )
    for x in to_update:
        this_registration = Registration.objects.using(db_alias).get(
            id=x.get('finalRegistration')
        )
        this_registration.data.update({'0034__invoice__id': str(x.get('id'))})
        this_registration.save()

    to_update_items = InvoiceItem.objects.filter(
        finalEventRegistration__isnull=False
    ).values('id', 'finalEventRegistration')
    for x in to_update_items:
        this_eventreg = EventRegistration.objects.using(db_alias).get(
            id=x.get('finalEventRegistration')
        )
        this_eventreg.data.update({'0034__invoiceitem__id': str(x.get('id'))})
        this_eventreg.save()


def reverse_reg_data(apps, schema_editor):
    '''
    Remove the JSON field that contains invoice linkages for this registration.
    '''
    Registration = apps.get_model("core", "Registration")
    EventRegistration = apps.get_model("core", "EventRegistration")
    db_alias = schema_editor.connection.alias

    to_update = Registration.objects.using(db_alias).filter(data__isnull=False)
    for x in to_update:
        if x.data.pop('0034__invoice__id', None):
            x.save()

    to_update_eventreg = EventRegistration.objects.using(db_alias).filter(
        data__isnull=False
    )
    for x in to_update_eventreg:
        if x.data.pop('0034__invoiceitem__id', None):
            x.save()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0033_auto_20200124_1349'),
    ]

    operations = [
        migrations.RunPython(update_reg_data, reverse_reg_data),
    ]
