# Generated by Django 3.1.6 on 2021-02-06 03:31

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0037_remove_registration_expirationdate'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='eventregistration',
            name='price',
        ),
        migrations.RemoveField(
            model_name='registration',
            name='priceWithDiscount',
        ),
    ]
