# Generated by Django 3.2.16 on 2022-11-06 20:52

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.expressions


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0053_auto_20220818_0035'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventAddOn',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0)),
                ('allocationType', models.CharField(choices=[('F', 'Fixed dollar allocation'), ('P', 'Fixed percentage allocation'), ('R', 'Allocation based on individual event default prices')], default='F', help_text='How is registration revenue allocated to this event?', max_length=1, verbose_name='Revenue allocation type')),
                ('allocationAmount', models.FloatField(blank=True, default=0, help_text='Enter the fixed amount or percentage (out of 100) of revenue that will be allocated to this event. This field is ignored if allocation is based on event default prices.', null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Allocation amount')),
            ],
            options={
                'verbose_name': 'Event add-on',
                'verbose_name_plural': 'Event add-ons',
                'ordering': ('order',),
            },
        ),
        migrations.AddField(
            model_name='invoiceitem',
            name='parent_item',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='child_items', to='core.invoiceitem'),
        ),
        migrations.AddConstraint(
            model_name='invoiceitem',
            constraint=models.CheckConstraint(check=models.Q(('parent_item', django.db.models.expressions.F('id')), _negated=True), name='no_self_parent_items'),
        ),
        migrations.AddField(
            model_name='eventaddon',
            name='addOnEvent',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='addon_of', to='core.event', verbose_name='Event'),
        ),
        migrations.AddField(
            model_name='eventaddon',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.event', verbose_name='Event'),
        ),
        migrations.AddConstraint(
            model_name='eventaddon',
            constraint=models.UniqueConstraint(fields=('event', 'addOnEvent'), name='unique_addon_per_event'),
        ),
        migrations.AddConstraint(
            model_name='eventaddon',
            constraint=models.CheckConstraint(check=models.Q(('addOnEvent', django.db.models.expressions.F('event')), _negated=True), name='no_self_addons'),
        ),
    ]
