from django.apps import apps as django_apps
from django.db import migrations


def _read_rate(Preference, section, name):
    ''' Read a former tax rate preference directly from the preferences table. '''
    row = Preference.objects.filter(section=section, name=name).first()
    try:
        return float(row.raw_value) if row and row.raw_value else 0.0
    except (TypeError, ValueError):
        return 0.0


def migrate_tax_preferences(apps, schema_editor):
    '''
    Sales tax rates were formerly set by site-wide preferences for class
    series, public events, private lessons, and merchandise. Rates are now
    defined by tax jurisdictions, and nothing is taxed unless a jurisdiction
    applies. So that an existing site continues to charge exactly the same
    tax after upgrading, this creates a default jurisdiction that reproduces
    the former preferences, and makes it the default jurisdiction for the site.

    Formerly, the public event rate applied to every event that was not a class
    series, so it becomes the default rate for the jurisdiction. Rules are then
    added for anything that had a different rate.
    '''
    Preference = apps.get_model('dynamic_preferences', 'GlobalPreferenceModel')
    TaxJurisdiction = apps.get_model('core', 'TaxJurisdiction')
    TaxRule = apps.get_model('core', 'TaxRule')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    public_rate = _read_rate(Preference, 'registration', 'publicEventSalesTaxRate')

    # (app label, model name, former rate) for everything that had its own rate.
    others = [
        ('core', 'series', _read_rate(Preference, 'registration', 'seriesSalesTaxRate')),
    ]
    if django_apps.is_installed('danceschool.private_lessons'):
        others.append((
            'private_lessons', 'privatelessonevent',
            _read_rate(Preference, 'privateLessons', 'salesTaxRate')
        ))
    if django_apps.is_installed('danceschool.merch'):
        others.append((
            'merch', 'merchitem',
            _read_rate(Preference, 'registration', 'merchSalesTaxRate')
        ))

    has_tax = public_rate > 0 or any(rate > 0 for _, _, rate in others)

    if has_tax and not TaxJurisdiction.objects.exists():
        jurisdiction = TaxJurisdiction.objects.create(
            name='Default', defaultRate=public_rate,
            notes=(
                'Created automatically from the sales tax rate preferences ' +
                'that were in use before tax jurisdictions were introduced.'
            ),
        )
        for app_label, model, rate in others:
            if rate != public_rate:
                content_type, _ = ContentType.objects.get_or_create(
                    app_label=app_label, model=model
                )
                TaxRule.objects.create(
                    jurisdiction=jurisdiction, itemType=content_type, rate=rate
                )

        Preference.objects.update_or_create(
            section='registration', name='defaultTaxJurisdiction',
            defaults={'raw_value': str(jurisdiction.pk)},
        )

    # The merchandise preference is removed by the merch app's own migration,
    # which also needs to read it.
    Preference.objects.filter(
        section='registration',
        name__in=['seriesSalesTaxRate', 'publicEventSalesTaxRate'],
    ).delete()
    Preference.objects.filter(section='privateLessons', name='salesTaxRate').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0061_taxjurisdiction_event_taxrateoverride_and_more'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('dynamic_preferences', '0006_auto_20191001_2236'),
    ]

    operations = [
        migrations.RunPython(migrate_tax_preferences, migrations.RunPython.noop),
    ]
