from django.db import migrations, models


def existing_discounts_applied(apps, schema_editor):
    '''
    Set RegistrationDiscounts with a null value of applied to True.  Note that
    the reverse of this migration does nothing.
    '''
    RegistrationDiscount = apps.get_model("discounts", "RegistrationDiscount")
    db_alias = schema_editor.connection.alias
    RegistrationDiscount.objects.using(db_alias).filter(applied=None).update(
        applied=True
    )


class Migration(migrations.Migration):

    dependencies = [
        ('discounts', '0011_auto_20210127_2052'),
    ]

    operations = [
        migrations.RunPython(
            existing_discounts_applied, migrations.RunPython.noop
        ),
        migrations.AlterField(
            model_name='registrationdiscount',
            name='applied',
            field=models.BooleanField(null=False, default=False, verbose_name='Use finalized'),
        ),
    ]
