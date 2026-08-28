from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dict", "0026_articlelink_kind"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArticleIndexTranslateSnapshot",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "batch_id",
                    models.CharField(
                        db_index=True, max_length=64, verbose_name="Снимок"
                    ),
                ),
                (
                    "rus_word",
                    models.CharField(
                        blank=True,
                        default=None,
                        max_length=255,
                        null=True,
                        verbose_name="Перевод",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "article",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="dict.article",
                    ),
                ),
            ],
            options={
                "verbose_name": "Снимок перевода",
                "verbose_name_plural": "Снимки переводов",
            },
        ),
        migrations.AddIndex(
            model_name="articleindextranslatesnapshot",
            index=models.Index(
                fields=["batch_id", "article"],
                name="dict_articl_batch_i_6a8f0d_idx",
            ),
        ),
    ]
