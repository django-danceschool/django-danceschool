from django.db import migrations, models


def existing_vouchers_applied(apps, schema_editor):
    '''
    Set VoucherUses with a null value of applied to True.  Note that the reverse
    of this migration does nothing.
    '''
    VoucherUse = apps.get_model("vouchers", "VoucherUse")
    db_alias = schema_editor.connection.alias
    VoucherUse.objects.using(db_alias).filter(applied=None).update(
        applied= True
    )


class Migration(migrations.Migration):

    dependencies = [
        ('vouchers', '0011_auto_20210127_2052'),
    ]

    operations = [
        migrations.RunPython(
            existing_vouchers_applied, migrations.RunPython.noop
        ),
        migrations.AlterField(
            model_name='voucheruse',
            name='applied',
            field=models.BooleanField(
                null=False, default=False, verbose_name='Use finalized'
            ),
        ),
    ]
