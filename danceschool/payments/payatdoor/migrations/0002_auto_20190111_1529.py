# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2019-01-11 20:29
from __future__ import unicode_literals

import cms.models.fields
from django.db import migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('payatdoor', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payatdoorformmodel',
            name='successPage',
            field=cms.models.fields.PageField(help_text='When the user returns to the site after a successful transaction, send them to this page.', on_delete=django.db.models.deletion.CASCADE, related_name='successPageForPayAtDoor', to='cms.Page', verbose_name='Success Page'),
        ),
    ]