from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dict", "0028_delete_articleindextranslatesnapshot"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="articlesemanticfield",
            index=models.Index(
                fields=["field", "from_translation"],
                name="dict_asf_field_from_tr_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="articlelink",
            index=models.Index(
                fields=["to_article", "kind"],
                name="dict_alink_to_kind_idx",
            ),
        ),
    ]
