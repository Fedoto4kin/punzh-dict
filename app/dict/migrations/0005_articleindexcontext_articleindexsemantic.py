# Generated by Django 3.1.7 on 2021-04-09 12:58

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dict', '0004_auto_20210408_1611'),
    ]

    operations = [
        migrations.CreateModel(
            name='ArticleIndexSemantic',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('word', models.CharField(blank=True, default=None, max_length=255, null=True)),
                ('article', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dict.article')),
            ],
            options={
                'unique_together': {('word', 'article')},
            },
        ),
        migrations.CreateModel(
            name='ArticleIndexContext',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('word', models.CharField(blank=True, default=None, max_length=255, null=True)),
                ('article', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dict.article')),
            ],
            options={
                'unique_together': {('word', 'article')},
            },
        ),
    ]