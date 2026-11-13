"""Export offline mobile package: dict.sqlite + manifest.json."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from dict.mobile import export_mobile_package


class Command(BaseCommand):
    help = (
        "Собрать офлайн-пакет для mobile: dict.sqlite + manifest.json "
        "(без семантики / AI / rus_lemmas). См. docs/plans/mobile-offline.md."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--out",
            type=str,
            default="mobile_pack",
            help="Каталог для dict.sqlite и manifest.json (создаётся при необходимости).",
        )

    def handle(self, *args, **options):
        out = Path(options["out"])
        try:
            package = export_mobile_package(out)
        except OSError as exc:
            raise CommandError(f"Не удалось записать пакет в {out}: {exc}") from exc

        m = package.manifest
        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {package.db_path} ({m['size']} bytes, "
                f"sha256={m['sha256'][:12]}…) schema={m['schema_version']} "
                f"data_version={m['data_version']}"
            )
        )
        self.stdout.write(f"Manifest: {package.manifest_path}")
