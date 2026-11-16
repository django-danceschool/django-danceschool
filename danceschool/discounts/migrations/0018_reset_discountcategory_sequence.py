from django.core.management.color import no_style
from django.db import migrations


def reset_sequence(apps, schema_editor):
    '''
    The default discount category was created by an earlier migration with an
    explicit id of 1. On databases that use a sequence for new ids (such as
    PostgreSQL), that does not advance the sequence, so the first category
    created afterward was given an id of 1 as well, and it failed with a
    duplicate key error. This sets the sequence to follow the highest id that
    is in use. It does nothing on databases that do not need it.
    '''
    DiscountCategory = apps.get_model('discounts', 'DiscountCategory')
    connection = schema_editor.connection
    statements = connection.ops.sequence_reset_sql(no_style(), [DiscountCategory])
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


class Migration(migrations.Migration):

    dependencies = [
        ('discounts', '0017_discountcombo_voucherid'),
    ]

    operations = [
        migrations.RunPython(reset_sequence, migrations.RunPython.noop),
    ]
