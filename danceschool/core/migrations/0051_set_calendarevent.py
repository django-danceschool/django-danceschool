from django.conf import settings
from django.db import migrations, models
from django.db.models import Q, F, Case, When


def set_calendarevent(apps, schema_editor):
    '''
    Events for which the calendarEvent flag is not set are assumed to be shown
    on the calendar unless they are linkOnly or hidden.
    '''
    Event = apps.get_model("core", "Event")
    db_alias = schema_editor.connection.alias

    to_update = Event.objects.using(db_alias).filter(
        calendarEvent__isnull=True
    ).annotate(
        statusRule=Case(
            When(Q(status__in=['L', 'X']), then=False),
            default=True, output_field=models.BooleanField()
        )
    )
    
    to_update.update(calendarEvent=F('statusRule'))


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0050_auto_20210323_2353'),
    ]

    operations = [
        migrations.RunPython(set_calendarevent, migrations.RunPython.noop),
    ]
