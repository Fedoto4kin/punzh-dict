# Generated by Django 3.1.7 on 2022-11-06 17:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dict', '0010_tag_level'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tag',
            name='tag',
            field=models.CharField(db_index=True, max_length=255),
        ),
    ]
