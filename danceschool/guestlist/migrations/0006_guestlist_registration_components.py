from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0059_alter_classdescription_description_and_more'),
        ('guestlist', '0005_guestlistname_email'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='GuestListComponent',
            new_name='GuestListStaffComponent',
        ),
        migrations.AlterModelOptions(
            name='guestliststaffcomponent',
            options={
                'ordering': ('guestList', 'admissionRule'),
                'verbose_name': 'Guest list staff component',
                'verbose_name_plural': 'Guest list staff components',
            },
        ),
        migrations.AlterField(
            model_name='guestliststaffcomponent',
            name='guestList',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(class)s_set',
                to='guestlist.guestlist', verbose_name='Guest list'
            ),
        ),
        migrations.AlterField(
            model_name='guestliststaffcomponent',
            name='admissionRule',
            field=models.CharField(
                choices=[
                    ('Always', 'Always added to guest list'),
                    ('EventOnly', 'Add if the person is a staff member for this event'),
                    ('Day', 'Add if the person is a staff member on that day'),
                    ('Week', 'Add if the person is a staff member in that week'),
                    ('Month', 'Add if the person is a staff member in that month'),
                    ('Year', 'Add if the person is a staff member in that year'),
                    (
                        'Rolling',
                        'Add if the person is a staff member within a specified number of days'
                    ),
                ],
                max_length=10, verbose_name='Event admission rule'
            ),
        ),
        migrations.AddField(
            model_name='guestliststaffcomponent',
            name='daysBefore',
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text=(
                    'For rolling admission rules only: how many days before the '
                    'event being checked into the qualifying participation may occur.'
                ),
                null=True, verbose_name='Days before'
            ),
        ),
        migrations.AddField(
            model_name='guestliststaffcomponent',
            name='daysAfter',
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text=(
                    'For rolling admission rules only: how many days after the '
                    'event being checked into the qualifying participation may occur.'
                ),
                null=True, verbose_name='Days after'
            ),
        ),
        migrations.CreateModel(
            name='GuestListRegistrationComponent',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False,
                        verbose_name='ID'
                    )
                ),
                (
                    'admissionRule',
                    models.CharField(
                        choices=[
                            (
                                'Day',
                                'Add if the person is registered for a qualifying event on that day'
                            ),
                            (
                                'Week',
                                'Add if the person is registered for a qualifying event in that week'
                            ),
                            (
                                'Month',
                                'Add if the person is registered for a qualifying event in that month'
                            ),
                            (
                                'Year',
                                'Add if the person is registered for a qualifying event in that year'
                            ),
                            (
                                'Rolling',
                                'Add if the person is registered for a qualifying event within a '
                                'specified number of days'
                            ),
                        ],
                        max_length=10, verbose_name='Event admission rule'
                    )
                ),
                (
                    'daysBefore',
                    models.PositiveSmallIntegerField(
                        blank=True,
                        help_text=(
                            'For rolling admission rules only: how many days before the '
                            'event being checked into the qualifying participation may occur.'
                        ),
                        null=True, verbose_name='Days before'
                    )
                ),
                (
                    'daysAfter',
                    models.PositiveSmallIntegerField(
                        blank=True,
                        help_text=(
                            'For rolling admission rules only: how many days after the '
                            'event being checked into the qualifying participation may occur.'
                        ),
                        null=True, verbose_name='Days after'
                    )
                ),
                (
                    'guestList',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='%(class)s_set',
                        to='guestlist.guestlist', verbose_name='Guest list'
                    )
                ),
                (
                    'eventCategories',
                    models.ManyToManyField(
                        blank=True,
                        help_text=(
                            'Registration for a public event in one of these categories '
                            'admits the customer to events on this guest list.'
                        ),
                        to='core.publiceventcategory',
                        verbose_name='Qualifying public event categories'
                    )
                ),
                (
                    'seriesCategories',
                    models.ManyToManyField(
                        blank=True,
                        help_text=(
                            'Registration for a class series in one of these categories '
                            'admits the customer to events on this guest list.'
                        ),
                        to='core.seriescategory',
                        verbose_name='Qualifying series categories'
                    )
                ),
            ],
            options={
                'ordering': ('guestList', 'admissionRule'),
                'verbose_name': 'Guest list registration component',
                'verbose_name_plural': 'Guest list registration components',
            },
        ),
    ]
