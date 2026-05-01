from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('private_events', '0004_auto_20190322_2346'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventreminder',
            name='scheduledTaskId',
            field=models.CharField(blank=True, editable=False, max_length=100, null=True, verbose_name='Scheduled task ID'),
        ),
    ]
