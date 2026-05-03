from django.db import migrations


def populate_placeholder_source(apps, schema_editor):
    """
    Ensure every Register's placeholder has content_type/object_id pointing
    back to its owning Register instance.  CMS migration 0033 does this for
    placeholders that existed at migration time, but any created afterwards via
    the old PlaceholderField.pre_save() would have been left without a source.
    """
    db_alias = schema_editor.connection.alias
    Register = apps.get_model('register', 'Register')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    ct = ContentType.objects.using(db_alias).get(
        app_label=Register._meta.app_label,
        model=Register._meta.model_name,
    )

    for register in Register.objects.using(db_alias).select_related('placeholder'):
        if register.placeholder_id is None:
            continue
        ph = register.placeholder
        if ph.content_type_id != ct.pk or ph.object_id != register.pk:
            ph.content_type_id = ct.pk
            ph.object_id = register.pk
            ph.save(update_fields=['content_type_id', 'object_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('register', '0010_alter_registereventpluginmodel_cmsplugin_ptr_and_more'),
        ('cms', '0033_placeholder_source_data_migration'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(
            populate_placeholder_source,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name='register',
            name='placeholder',
        ),
    ]
