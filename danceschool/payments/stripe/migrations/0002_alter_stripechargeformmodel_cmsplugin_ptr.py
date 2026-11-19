import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0035_auto_20230822_2208_squashed_0036_auto_20240311_1028'),
        ('stripe', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stripechargeformmodel',
            name='cmsplugin_ptr',
            field=models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, related_name='%(app_label)s_%(class)s', serialize=False, to='cms.cmsplugin'),
        ),
    ]
