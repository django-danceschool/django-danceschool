# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-03-22 21:29
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('financial', '0013_auto_20181219_2044'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='revenueitem',
            options={'ordering': ['-accrualDate'], 'permissions': (('mark_revenues_received', 'Mark revenues as received at the time of submission'), ('export_financial_data', 'Export detailed financial transaction information to CSV'), ('view_finances_bymonth', 'View school finances month-by-month'), ('view_finances_byevent', 'View school finances by Event'), ('view_finances_detail', 'View school finances as detailed statement')), 'verbose_name': 'Revenue item', 'verbose_name_plural': 'Revenue items'},
        ),
    ]