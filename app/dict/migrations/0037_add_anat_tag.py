from django.db import connection, migrations


def add_anat_tag(apps, schema_editor):
    Tag = apps.get_model("dict", "Tag")
    if Tag.objects.filter(tag="анат.").exists():
        return
    # Prefer pk=72 to match dict_seed.json; fall back if that id is taken.
    fields = {
        "tag": "анат.",
        "name": "анатомия",
        "type": 3,
        "sorting": None,
        "level": 0,
    }
    if not Tag.objects.filter(pk=72).exists():
        Tag.objects.create(id=72, **fields)
    else:
        Tag.objects.create(**fields)

    # Explicit id insert does not advance the serial; bump it for later creates.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT setval(pg_get_serial_sequence('dict_tag', 'id'), "
            "GREATEST((SELECT COALESCE(MAX(id), 1) FROM dict_tag), 1))"
        )


def remove_anat_tag(apps, schema_editor):
    Tag = apps.get_model("dict", "Tag")
    Tag.objects.filter(tag="анат.").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("dict", "0036_articleindextranslate_rus_lemmas"),
    ]

    operations = [
        migrations.RunPython(add_anat_tag, remove_anat_tag),
    ]
