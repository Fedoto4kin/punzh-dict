# Generated by Django 3.1.7 on 2021-03-27 11:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dict', '0003_remove_article_definition'),
    ]

    operations = [
        migrations.AlterField(
            model_name='article',
            name='word',
            field=models.CharField(db_index=True, max_length=255, unique=True),
        ),
    ]