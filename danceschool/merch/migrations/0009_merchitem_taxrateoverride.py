import django.core.validators
from django.db import migrations, models


def clear_default_rates(apps, schema_editor):
    '''
    Every merchandise item formerly stored its own sales tax rate, which was
    filled in from the merchandise sales tax preference when the item was
    created. That field is now an optional override. An item whose rate matches
    the former preference was simply using the default, so its override is
    cleared and it will follow the rules of the applicable tax jurisdiction
    (the core app's migration reproduces the former merchandise rate there).
    An item with any other rate keeps it as an override.
    '''
    Preference = apps.get_model('dynamic_preferences', 'GlobalPreferenceModel')
    MerchItem = apps.get_model('merch', 'MerchItem')

    row = Preference.objects.filter(
        section='registration', name='merchSalesTaxRate'
    ).first()
    try:
        default_rate = float(row.raw_value) if row and row.raw_value else 0.0
    except (TypeError, ValueError):
        default_rate = 0.0

    MerchItem.objects.filter(taxRateOverride=default_rate).update(taxRateOverride=None)

    Preference.objects.filter(
        section='registration', name='merchSalesTaxRate'
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('merch', '0008_optional_category_and_plural_name'),
        ('core', '0062_migrate_tax_rate_preferences'),
        ('dynamic_preferences', '0006_auto_20191001_2236'),
    ]

    operations = [
        migrations.RenameField(
            model_name='merchitem',
            old_name='salesTaxRate',
            new_name='taxRateOverride',
        ),
        migrations.AlterField(
            model_name='merchitem',
            name='taxRateOverride',
            field=models.FloatField(blank=True, help_text="Leave blank to apply the tax rules of the jurisdiction in which this item is sold. To override those rules for this item only, enter a whole number percentage (e.g. enter '6' for 6%), or enter 0 if this item is exempt from tax.", null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Sales tax rate override'),
        ),
        migrations.RunPython(clear_default_rates, migrations.RunPython.noop),
    ]
