# Generated by Django 4.1 on 2023-11-16 10:25

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0001_initial'),
        ('ims', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='errorticket',
            name='branch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='account.branch'),
        ),
        migrations.AddField(
            model_name='errorticket',
            name='pos',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='error_tickets_reported', to='account.pos'),
        ),
        migrations.AlterField(
            model_name='errorticket',
            name='staff',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='error_tickets_assigned', to='account.pos'),
        ),
    ]