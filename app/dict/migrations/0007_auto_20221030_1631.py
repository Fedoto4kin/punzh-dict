# Generated by Django 3.1.7 on 2022-10-30 16:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dict', '0006_auto_20221030_1556'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tag', models.CharField(db_index=True, max_length=255, unique=True)),
                ('name', models.TextField()),
                ('type', models.IntegerField(choices=[(1, 'Населенные пункты'), (2, 'Часть речи'), (3, 'Пометы')])),
                ('articles', models.ManyToManyField(to='dict.Article')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.DeleteModel(
            name='ArticleTag',
        ),
    ]