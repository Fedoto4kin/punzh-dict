# Generated by Django 3.1.7 on 2022-11-06 12:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dict', '0007_auto_20221030_1631'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='tag',
            name='articles',
        ),
        migrations.AlterField(
            model_name='tag',
            name='type',
            field=models.IntegerField(choices=[(1, 'Населенные пункты'), (2, 'Часть речи'), (3, 'Пометы'), (4, 'Говоры'), (5, 'Другое')]),
        ),
    ]
