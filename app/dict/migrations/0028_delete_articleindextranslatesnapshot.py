from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("dict", "0027_articleindextranslatesnapshot"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ArticleIndexTranslateSnapshot",
        ),
    ]
