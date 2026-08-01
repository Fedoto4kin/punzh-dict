from django.db import migrations


def migrate_linked_articles(apps, schema_editor):
    Article = apps.get_model("dict", "Article")
    ArticleLink = apps.get_model("dict", "ArticleLink")

    for article in Article.objects.all():
        if article.linked_article_id:
            # Прямая связь
            ArticleLink.objects.get_or_create(
                from_article_id=article.id,
                to_article_id=article.linked_article_id,
            )

            # Обратная связь
            ArticleLink.objects.get_or_create(
                from_article_id=article.linked_article_id,
                to_article_id=article.id,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("dict", "0015_articlelink"),
    ]

    operations = [
        migrations.RunPython(migrate_linked_articles, migrations.RunPython.noop),
    ]
