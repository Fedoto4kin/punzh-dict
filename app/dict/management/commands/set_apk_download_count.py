"""Set or seed the APK download counter (e.g. from nginx access logs)."""

from __future__ import annotations

import gzip
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from dict.models import ApkDownloadStat

# Combined / common log: … "GET /mobile-pack/punzh-dict-latest.apk HTTP/1.1" 200 …
_APK_HIT = re.compile(
    r'"GET\s+/mobile-pack/punzh-dict-latest\.apk(?:\?\S*)?\s+HTTP/[\d.]+"\s+(200|206)\b'
)


def count_apk_hits_in_log(path: Path) -> int:
    opener = gzip.open if path.name.endswith(".gz") else open
    mode = "rt" if path.name.endswith(".gz") else "r"
    total = 0
    with opener(path, mode, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if _APK_HIT.search(line):
                total += 1
    return total


class Command(BaseCommand):
    help = (
        "Set ApkDownloadStat.count. Pass an integer, or --from-log PATH "
        "(nginx access log / .gz; counts GET 200/206 for punzh-dict-latest.apk)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "count",
            nargs="?",
            type=int,
            help="Absolute value to store (e.g. historical nginx hit count).",
        )
        parser.add_argument(
            "--from-log",
            action="append",
            default=[],
            metavar="PATH",
            help="Nginx access log file (repeatable; .gz ok). Sums matching hits.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the value that would be stored; do not write.",
        )

    def handle(self, *args, **options):
        log_paths = options["from_log"]
        count = options["count"]

        if log_paths:
            total = 0
            for raw in log_paths:
                path = Path(raw)
                if not path.is_file():
                    raise CommandError(f"Not a file: {path}")
                n = count_apk_hits_in_log(path)
                self.stdout.write(f"{path}: {n}")
                total += n
            value = total
        elif count is not None:
            value = count
        else:
            raise CommandError("Pass COUNT or --from-log PATH")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"dry-run: would set count={value}"))
            return

        obj = ApkDownloadStat.set_count(value)
        self.stdout.write(self.style.SUCCESS(f"ApkDownloadStat.count = {obj.count}"))
