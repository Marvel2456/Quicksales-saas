from django.db import migrations


def drop_orphaned_has_variations(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(
            'ALTER TABLE ims_product DROP COLUMN IF EXISTS has_variations;'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('ims', '0021_historicalinventory_variation_quantities_and_more'),
    ]

    operations = [
        migrations.RunPython(drop_orphaned_has_variations, migrations.RunPython.noop),
    ]
