# Migrated from danceschool.register migration 0011_public_register_event_plugin
# (originally generated 2026-03-16). Models moved to danceschool.core so that
# core remains the only required app in the danceschool project.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0041_alter_pageurl_unique_together_pageurl_site_and_more'),
        ('core', '0057_event_registrationopendate'),
    ]

    operations = [
        migrations.CreateModel(
            name='PublicRegisterNavPluginModel',
            fields=[
                ('cmsplugin_ptr', models.OneToOneField(
                    auto_created=True, on_delete=django.db.models.deletion.CASCADE,
                    parent_link=True, primary_key=True,
                    related_name='%(app_label)s_%(class)s', serialize=False,
                    to='cms.cmsplugin',
                )),
                ('title', models.CharField(
                    blank=True, default='',
                    help_text='Optional text displayed at the left edge of the navbar. Leave blank to show navigation links only.',
                    max_length=200, verbose_name='Navbar brand text',
                )),
            ],
            options={
                'verbose_name': 'Public register navigation bar',
                'verbose_name_plural': 'Public register navigation bars',
            },
            bases=('cms.cmsplugin',),
        ),
        migrations.CreateModel(
            name='PublicRegisterEventPluginModel',
            fields=[
                ('cmsplugin_ptr', models.OneToOneField(
                    auto_created=True, on_delete=django.db.models.deletion.CASCADE,
                    parent_link=True, primary_key=True,
                    related_name='%(app_label)s_%(class)s', serialize=False,
                    to='cms.cmsplugin',
                )),
                ('eventType', models.CharField(
                    choices=[('B', 'Class Series and Public Events'), ('S', 'Only Class Series'), ('P', 'Only Public Events')],
                    default='B', max_length=1, verbose_name='Limit to event type',
                )),
                ('limitNumber', models.PositiveSmallIntegerField(
                    blank=True, help_text='Leave blank for no restriction',
                    null=True, verbose_name='Limit number',
                )),
                ('sortOrder', models.CharField(
                    choices=[('A', 'Ascending'), ('D', 'Descending')],
                    default='A',
                    help_text='This may be overridden by the particular template in use',
                    max_length=1, verbose_name='Sort by start time',
                )),
                ('occursWithinDays', models.PositiveSmallIntegerField(
                    blank=True, default=0,
                    help_text='If set, then the register will only include events that have an occurrence within this many days in the future of the register date(usually) the current date. The default of 0 limits to only events that occur on the register date. Leave blank for no restriction.',
                    null=True, verbose_name='Event occurs within __ days',
                )),
                ('limitTypeStart', models.CharField(
                    choices=[('S', 'Event start date'), ('E', 'Event end date')],
                    default='E', max_length=1, verbose_name='Limit interval start by',
                )),
                ('daysStart', models.SmallIntegerField(
                    blank=True,
                    help_text='(E.g. enter -30 for an interval that starts with 30 days prior to today) Leave blank for no limit, or enter 0 to limit to future events',
                    null=True, verbose_name='Interval limited to __ days from present',
                )),
                ('startDate', models.DateField(
                    blank=True,
                    help_text='Leave blank for no limit (overrides relative interval limits)',
                    null=True, verbose_name='Exact interval start date',
                )),
                ('limitTypeEnd', models.CharField(
                    choices=[('S', 'Event start date'), ('E', 'Event end date')],
                    default='S', max_length=1, verbose_name='Limit interval end by',
                )),
                ('daysEnd', models.SmallIntegerField(
                    blank=True,
                    help_text='(E.g. enter 30 for an interval that ends 30 days from today) Leave blank for no limit, or enter 0 to limit to past events',
                    null=True, verbose_name='Interval limited to __ days from present',
                )),
                ('endDate', models.DateField(
                    blank=True,
                    help_text='Leave blank for no limit (overrides relative interval limits)',
                    null=True, verbose_name='Exact interval end date ',
                )),
                ('registrationOpenLimit', models.CharField(
                    choices=[('O', 'Open for registration only'), ('C', 'Closed for registration only'), ('B', 'Both open and closed events')],
                    default='O', max_length=1,
                    verbose_name='Limit to open/closed for registration only',
                )),
                ('weekday', models.PositiveSmallIntegerField(
                    blank=True,
                    choices=[(0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday')],
                    null=True, verbose_name='Limit to weekday',
                )),
                ('autoCheckIn', models.CharField(
                    choices=[('0', 'No automatic check-in'), ('E', 'Current event occurrence (next ending time)'), ('S', 'Current event occurrence (next starting time)'), ('F', 'Entire event')],
                    default='E', max_length=1,
                    verbose_name='Automatic event/occurrence check-in when registration is complete',
                )),
                ('title', models.CharField(
                    blank=True, default='Upcoming Events', max_length=250,
                    verbose_name='Section title',
                )),
                ('cssClasses', models.CharField(
                    blank=True,
                    help_text='Classes are applied to the surrounding &lt;div&gt;',
                    max_length=250, null=True, verbose_name='Custom CSS classes',
                )),
                ('template', models.CharField(
                    blank=True, max_length=250, null=True,
                    verbose_name='Plugin template',
                )),
                ('eventCategories', models.ManyToManyField(
                    blank=True, help_text='Leave blank for no restriction',
                    to='core.publiceventcategory',
                    verbose_name='Limit to public event categories',
                )),
                ('levels', models.ManyToManyField(
                    blank=True, help_text='Leave blank for no restriction',
                    to='core.dancetypelevel',
                    verbose_name='Limit to type and levels',
                )),
                ('location', models.ManyToManyField(
                    blank=True, help_text='Leave blank for no restriction',
                    to='core.location', verbose_name='Limit to locations',
                )),
                ('seriesCategories', models.ManyToManyField(
                    blank=True, help_text='Leave blank for no restriction',
                    to='core.seriescategory',
                    verbose_name='Limit to series categories',
                )),
            ],
            options={
                'permissions': (('choose_custom_public_plugin_template', 'Can enter a custom plugin template for public register plugins.'),),
            },
            bases=('cms.cmsplugin',),
        ),
        migrations.CreateModel(
            name='PublicRegisterEventPluginChoice',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('optionLabel', models.CharField(
                    blank=True, default='',
                    help_text='Optional prefix shown before the role name, e.g. "Sign up as". Leave blank to show only the role name.',
                    max_length=100, verbose_name='Label prefix',
                )),
                ('soldOutRule', models.CharField(
                    choices=[('D', 'Display with sold-out label'), ('H', 'Hide sold-out choices')],
                    default='D', max_length=1,
                    verbose_name='Rule for sold-out choices',
                )),
                ('data', models.JSONField(
                    blank=True, default=dict,
                    help_text='Custom JSON stored with each registration produced by this choice. This value is kept server-side and is never transmitted through the browser, so it cannot be modified by users.',
                    verbose_name='Additional data attached to registrations',
                )),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('eventPlugin', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='core.publicregistereventpluginmodel',
                    verbose_name='Plugin',
                )),
            ],
            options={
                'ordering': ['order'],
            },
        ),
    ]
