# Generated by Django 2.1.7 on 2019-04-04 03:36

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import filer.fields.image


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_event_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='cashpaymentrecord',
            name='paymentMethod',
            field=models.CharField(default='Cash', max_length=30, verbose_name='Payment method'),
        ),
        migrations.AlterField(
            model_name='eventregistration',
            name='customer',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.Customer', verbose_name='Customer'),
        ),
        migrations.AlterField(
            model_name='registration',
            name='customer',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.Customer', verbose_name='Customer'),
        ),
        migrations.AlterField(
            model_name='registration',
            name='firstName',
            field=models.CharField(max_length=100, null=True, verbose_name='First name'),
        ),
        migrations.AlterField(
            model_name='registration',
            name='lastName',
            field=models.CharField(max_length=100, null=True, verbose_name='Last name'),
        ),
        migrations.AlterField(
            model_name='staffmember',
            name='image',
            field=filer.fields.image.FilerImageField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='staff_image', to=settings.FILER_IMAGE_MODEL, verbose_name='Staff photo'),
        ),
    ]
