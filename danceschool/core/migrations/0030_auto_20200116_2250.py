# Generated by Django 2.2.6 on 2020-01-17 03:50

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0029_auto_20200106_2246'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventstaffmember',
            name='data',
            field=models.JSONField(blank=True, default=dict, verbose_name='Additional data'),
        ),
        migrations.CreateModel(
            name='EventCheckIn',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('checkInType', models.CharField(choices=[('E', 'Event'), ('O', 'Event occurrence')], max_length=1, verbose_name='Check-in type')),
                ('firstName', models.CharField(max_length=100, null=True, verbose_name='First name')),
                ('lastName', models.CharField(max_length=100, null=True, verbose_name='Last name')),
                ('cancelled', models.BooleanField(blank=True, default=False, null=True, verbose_name='Check-in cancelled')),
                ('data', models.JSONField(blank=True, default=dict, verbose_name='Additional data')),
                ('creationDate', models.DateTimeField(auto_now_add=True, verbose_name='Creation date')),
                ('modifiedDate', models.DateTimeField(auto_now=True, verbose_name='Last modified')),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.Event', verbose_name='Event')),
                ('eventRegistration', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.EventRegistration', verbose_name='Event registration')),
                ('occurrence', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.EventOccurrence', verbose_name='Event occurrence')),
                ('submissionUser', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Submission User')),
            ],
            options={
                'verbose_name': 'Event check-in',
                'verbose_name_plural': 'Event check-ins',
            },
        ),
        migrations.AddConstraint(
            model_name='eventcheckin',
            constraint=models.UniqueConstraint(condition=models.Q(models.Q(('checkInType', 'E'), ('eventRegistration__isnull', False))), fields=('event', 'eventRegistration'), name='unique_event_eventreg_checkin'),
        ),
        migrations.AddConstraint(
            model_name='eventcheckin',
            constraint=models.UniqueConstraint(condition=models.Q(models.Q(('checkInType', 'O'), ('occurrence__isnull', False), ('eventRegistration__isnull', False))), fields=('event', 'occurrence', 'eventRegistration'), name='unique_occurrence_eventreg_checkin'),
        ),
        migrations.AddConstraint(
            model_name='eventcheckin',
            constraint=models.UniqueConstraint(condition=models.Q(models.Q(('checkInType', 'E'), ('eventRegistration__isnull', True), ('firstName__isnull', False), ('lastName__isnull', False))), fields=('event', 'firstName', 'lastName'), name='unique_event_name_checkin'),
        ),
        migrations.AddConstraint(
            model_name='eventcheckin',
            constraint=models.UniqueConstraint(condition=models.Q(models.Q(('checkInType', 'O'), ('occurrence__isnull', False), ('eventRegistration__isnull', True), ('firstName__isnull', False), ('lastName__isnull', False))), fields=('event', 'occurrence', 'firstName', 'lastName'), name='unique_occurrence_name_checkin'),
        ),
    ]
