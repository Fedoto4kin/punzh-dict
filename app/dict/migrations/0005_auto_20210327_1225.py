# Generated by Django 3.1.7 on 2021-03-27 12:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dict', '0004_auto_20210327_1121'),
    ]

    operations = [
        migrations.AlterField(
            model_name='article',
            name='first_letter',
            field=models.CharField(db_index=True, max_length=1),
        ),
    ]
