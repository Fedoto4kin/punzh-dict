# Generated by Django 3.1.7 on 2021-12-08 17:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dict', '0007_auto_20211114_1409'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ArticleIndexContext',
            new_name='ArticleIndexTranslate',
        ),
        migrations.AlterModelOptions(
            name='article',
            options={'ordering': ['-id'], 'verbose_name': 'Слово', 'verbose_name_plural': 'Слова'},
        ),
        migrations.RenameField(
            model_name='articleindextranslate',
            old_name='word',
            new_name='rus_word',
        ),
        migrations.AlterField(
            model_name='article',
            name='article_html',
            field=models.TextField(default='', verbose_name='Словарная статья (html)'),
        ),
        migrations.AlterField(
            model_name='article',
            name='word',
            field=models.CharField(db_index=True, max_length=255, unique=True, verbose_name='Слово (ориг.)'),
        ),
        migrations.AlterField(
            model_name='article',
            name='word_normalized',
            field=models.CharField(blank=True, db_index=True, default=None, max_length=255, null=True, verbose_name='Коррекция заголовка'),
        ),
        migrations.AlterUniqueTogether(
            name='articleindextranslate',
            unique_together={('rus_word', 'article')},
        ),
        migrations.DeleteModel(
            name='ArticleIndexSemantic',
        ),
    ]
