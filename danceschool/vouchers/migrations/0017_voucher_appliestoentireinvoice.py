from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vouchers', '0016_auto_20210214_1815'),
    ]

    operations = [
        migrations.AddField(
            model_name='voucher',
            name='appliesToEntireInvoice',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'If this voucher is restricted to specific classes or events, '
                    'then by default it can only be used for registrations for '
                    'those classes or events. If checked, then once there is such '
                    'a registration, the voucher can be used for everything on the '
                    'invoice, including other registrations and merchandise.'
                ),
                verbose_name='Can be used for anything on the invoice',
            ),
        ),
    ]
