# Generated by Django 3.1.7 on 2022-11-06 15:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dict', '0009_tag_sorting'),
    ]

    operations = [
        migrations.AddField(
            model_name='tag',
            name='level',
            field=models.IntegerField(default=0),
        ),
    ]