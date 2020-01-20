from django.db import migrations


def forwards_func(apps, schema_editor):
    ''' Create check-in records for all checked-in EventRegistrations. '''
    EventCheckIn = apps.get_model("core", "EventCheckIn")
    EventRegistration = apps.get_model("core", "EventRegistration")
    db_alias = schema_editor.connection.alias

    create_list = [
        EventCheckIn(
            event=x.event, checkInType='E', cancelled=False,
            eventRegistration=x,
            firstName=x.registration.firstName, lastName=x.registration.lastName,
            data={'migration_0030': True}
        ) for x in EventRegistration.objects.using(db_alias).filter(checkedIn=True)
    ]

    EventCheckIn.objects.using(db_alias).bulk_create(create_list)


def reverse_func(apps, schema_editor):
    '''
    Mark EventRegistrations checkedIn if an existing event-level record exists
    for that EventRegistration.
    '''
    EventCheckIn = apps.get_model("core", "EventCheckIn")
    EventRegistration = apps.get_model("core", "EventRegistration")
    db_alias = schema_editor.connection.alias

    eventRegs = EventRegistration.objects.using(db_alias).filter(id__in=
        EventCheckIn.objects.using(db_alias).filter(
            checkInType='E', cancelled=False,
            eventRegistration__isnull=False,
        ).values_list('eventregistration__id', flat=True)
    )
    
    for reg in eventRegs:
        reg.checkedIn = True

    EventRegistration.objects.using(db_alias).bulk_update(eventRegs, ['checkedIn'],)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0030_auto_20200116_2250'),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func)
    ]
