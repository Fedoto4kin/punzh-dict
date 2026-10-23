# Generated manually for AI search LLM soft re-rank status.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dict", "0032_ai_search_job"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aisearchjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "queued"),
                    ("running", "running"),
                    ("ranking", "ranking"),
                    ("done", "done"),
                    ("error", "error"),
                    ("expired", "expired"),
                ],
                db_index=True,
                default="queued",
                max_length=16,
            ),
        ),
    ]
