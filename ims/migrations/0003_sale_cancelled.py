from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ims', '0002_org_scoped_uniques'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='cancelled',
            field=models.BooleanField(default=False),
        ),
    ]
