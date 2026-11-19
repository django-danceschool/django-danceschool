from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paypal', '0005_alter_paynowformmodel_cmsplugin_ptr'),
    ]

    operations = [
        migrations.AddField(
            model_name='paypalpaymentrecord',
            name='captureId',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Paypal Capture ID'),
        ),
    ]
