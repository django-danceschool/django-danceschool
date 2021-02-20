# Generated by Django 3.1.6 on 2021-02-17 19:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('door', '0006_doorregisterguestsearchpluginmodel'),
    ]

    operations = [
        migrations.AddField(
            model_name='doorregistereventpluginmodel',
            name='autoCheckIn',
            field=models.CharField(choices=[('0', 'No automatic check-in'), ('E', 'Current event occurrence (next ending time)'), ('S', 'Current event occurrence (next starting time)'), ('F', 'Entire event')], default='E', max_length=1, verbose_name='Automatic event/occurrence check-in when registration is complete'),
        ),
        migrations.AddField(
            model_name='doorregisterguestsearchpluginmodel',
            name='autoCheckIn',
            field=models.CharField(choices=[('0', 'No automatic check-in'), ('E', 'Current event occurrence (next ending time)'), ('S', 'Current event occurrence (next starting time)'), ('F', 'Entire event')], default='E', max_length=1, verbose_name='Automatic event/occurrence check-in when registration is complete'),
        ),
    ]
