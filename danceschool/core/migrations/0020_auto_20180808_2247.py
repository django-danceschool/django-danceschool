# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-08-09 02:47
from __future__ import unicode_literals

import danceschool.core.mixins
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_invoice_buyerpayssalestax'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomerGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='Group name')),
            ],
            options={
                'ordering': ('name',),
                'verbose_name': 'Customer group',
                'verbose_name_plural': 'Customer groups',
            },
            bases=(danceschool.core.mixins.EmailRecipientMixin, models.Model),
        ),
        migrations.AddField(
            model_name='customer',
            name='groups',
            field=models.ManyToManyField(blank=True, help_text='Customer groups may be used for group-specific discounts and vouchers, as well as for email purposes.', to='core.CustomerGroup', verbose_name='Customer groups'),
        ),
    ]
