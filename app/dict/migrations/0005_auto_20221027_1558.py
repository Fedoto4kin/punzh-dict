# Generated by Django 3.1.7 on 2022-10-27 15:58

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dict', '0004_article_linked_article'),
    ]

    operations = [
        migrations.AlterField(
            model_name='article',
            name='linked_article',
            field=models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.SET_NULL, to='dict.article', verbose_name='см.'),
        ),
    ]
