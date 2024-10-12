# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-11-09 21:31
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import multiselectfield.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ('filer', '0010_auto_20180414_2058'),
        ('cms', '0020_old_tree_cleanup'),
        ('core', '0024_staffmember_categories'),
    ]

    operations = [
        migrations.RenameModel('InstructorListPluginModel','StaffMemberListPluginModel'),
        migrations.RenameField(
            model_name='instructor',
            old_name='staffmember_ptr',
            new_name='staffMember',
        ),
        migrations.AlterField(
            model_name='instructor',
            name='staffMember',
            field=models.OneToOneField(default=1, on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to='core.StaffMember', verbose_name='Staff member'),
            preserve_default=False,
        ),
        migrations.RemoveField(
            model_name='staffmember',
            name='polymorphic_ctype',
        ),
        migrations.AlterField(
            model_name='instructor',
            name='availableForPrivates',
            field=models.BooleanField(default=True, help_text='Check this box if you would like to be listed as available for private lessons from students.', verbose_name='Available for private lessons'),
        ),
        migrations.AlterModelOptions(
            name='instructor',
            options={'permissions': (('update_instructor_bio', "Can update instructors' bio information"), ('view_own_instructor_stats', "Can view one's own statistics (if an instructor)"), ('view_other_instructor_stats', "Can view other instructors' statistics"), ('view_own_instructor_finances', "Can view one's own financial/payment data (if a staff member)"), ('view_other_instructor_finances', "Can view other staff members' financial/payment data")), 'verbose_name': 'Instructor', 'verbose_name_plural': 'Instructors'},
        ),
        migrations.AlterField(
            model_name='staffmemberlistpluginmodel',
            name='activeUpcomingOnly',
            field=models.BooleanField(default=False, verbose_name='Include only staff members with upcoming classes/events'),
        ),
        migrations.AlterField(
            model_name='staffmemberlistpluginmodel',
            name='bioRequired',
            field=models.BooleanField(default=False, verbose_name='Exclude staff members with no bio'),
        ),
        migrations.AlterField(
            model_name='staffmemberlistpluginmodel',
            name='cmsplugin_ptr',
            field=models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, related_name='core_staffmemberlistpluginmodel', serialize=False, to='cms.CMSPlugin'),
        ),
        migrations.AlterField(
            model_name='staffmemberlistpluginmodel',
            name='photoRequired',
            field=models.BooleanField(default=False, verbose_name='Exclude staff members with no photo'),
        ),
        migrations.AlterField(
            model_name='staffmemberlistpluginmodel',
            name='statusChoices',
            field=multiselectfield.db.fields.MultiSelectField(choices=[('R', 'Regular Instructor'), ('A', 'Assistant Instructor'), ('T', 'Instructor-in-training'), ('G', 'Guest Instructor'), ('Z', 'Former Guest Instructor'), ('X', 'Former/Retired Instructor'), ('H', 'Publicly Hidden')], default=['R', 'A', 'G'], max_length=13, verbose_name='Limit to Instructors with Status'),
        ),
        migrations.AlterField(
            model_name='instructor',
            name='status',
            field=models.CharField(choices=[('R', 'Regular Instructor'), ('A', 'Assistant Instructor'), ('T', 'Instructor-in-training'), ('G', 'Guest Instructor'), ('Z', 'Former Guest Instructor'), ('X', 'Former/Retired Instructor'), ('H', 'Publicly Hidden')], default='H', help_text='Instructor status affects the visibility of the instructor on the site, but is separate from the "categories" of event staffing on which compensation is based.', max_length=1, verbose_name='Instructor status'),
        ),
        migrations.AlterField(
            model_name='staffmember',
            name='categories',
            field=models.ManyToManyField(blank=True, help_text='When choosing staff members, the individuals available to staff will be limited based on the categories chosen here. If the individual is an instructor, also be sure to set the instructor information below.', to='core.EventStaffCategory', verbose_name='Included in staff categories'),
        ),
        migrations.CreateModel(
            name='SeriesStaffMember',
            fields=[
            ],
            options={
                'verbose_name': 'Series staff member',
                'verbose_name_plural': 'Series staff members',
                'proxy': True,
            },
            bases=('core.eventstaffmember',),
        ),
        migrations.AlterModelOptions(
            name='staffmember',
            options={'ordering': ('lastName', 'firstName'), 'permissions': (('view_staff_directory', 'Can access the staff directory view'), ('view_school_stats', "Can view statistics about the school's performance."), ('can_autocomplete_staffmembers', 'Able to use customer and staff member autocomplete features (in admin forms)')), 'verbose_name': 'Staff member', 'verbose_name_plural': 'Staff members'},
        ),
    ]
