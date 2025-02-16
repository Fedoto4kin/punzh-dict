from django.contrib.postgres.search import SearchVector
from django.db import migrations
from dict.models import ArticleIndexTranslate

def create_fulltext_index(apps, schema_editor):
    ArticleIndexTranslate = apps.get_model('dict', 'ArticleIndexTranslate')
    ArticleIndexTranslate.objects.update(
        search_vector=SearchVector('rus_word')
    )

class Migration(migrations.Migration):

    dependencies = [
        ('dict', '0013_auto_20250214_1633'),
    ]

    operations = [
        migrations.RunPython(create_fulltext_index),
    ]
