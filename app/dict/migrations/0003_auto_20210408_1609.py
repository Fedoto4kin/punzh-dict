# Generated by Django 3.1.7 on 2021-04-08 16:09

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dict', '0002_articlewordindex'),
    ]

    operations = [
        migrations.CreateModel(
            name='ArticleIndex',
            fields=[
                ('word', models.CharField(blank=True, default=None, max_length=255, null=True)),
                ('article', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dict.article')),
            ],
            options={
                'unique_together': {('word', 'article')},
            },
        ),
        migrations.RemoveField(
            model_name='articlewordindex',
            name='article',
        ),
        migrations.RemoveField(
            model_name='searchword',
            name='article',
        ),
        migrations.DeleteModel(
            name='ArticleSearchIndex',
        ),
        migrations.DeleteModel(
            name='ArticleWordIndex',
        ),
        migrations.DeleteModel(
            name='SearchWord',
        ),
    ]