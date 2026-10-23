"""
Interactive REPL and one-shot CLI for AI search query parsing.

    docker exec -i -w /app punzh_django python manage.py ai_query
    docker exec -i -w /app punzh_django python manage.py ai_query --once "коза"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from dict.ai.query_parse import parse_query
from dict.ai.telemetry import serialize_ai_search_event

BENCHMARKS_PATH = (
    Path(settings.BASE_DIR)
    / "dict"
    / "fixtures"
    / "custom"
    / "ai_query_benchmarks.json"
)


class Command(BaseCommand):
    help = "Разбор AI-запроса: REPL или --once / --benchmark."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            type=str,
            default=None,
            help="Один запрос и выход.",
        )
        parser.add_argument(
            "--benchmark",
            action="store_true",
            help="Прогон эталонов из ai_query_benchmarks.json.",
        )
        parser.add_argument(
            "--log-file",
            type=str,
            default="",
            help="Append JSONL events to this path.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Полный debug + raw.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Только display и краткие counts.",
        )
        parser.add_argument(
            "--preview",
            action="store_true",
            help="Сразу включить preview групп (фаза B).",
        )

    def handle(self, *args, **options):
        self.verbose = bool(options["verbose"])
        self.quiet = bool(options["quiet"]) and not self.verbose
        self.preview = bool(options["preview"])
        self.log_path = (options.get("log_file") or "").strip()
        self.history = []
        self.last_result = None
        self.last_event = None
        self.last_groups = None
        self.last_fallback_count = None

        if options["benchmark"]:
            self._run_benchmark()
            return

        once = options.get("once")
        if once is not None:
            self._handle_query(once)
            return

        self._repl()

    def _repl(self):
        self.stdout.write(
            "ai_query REPL. :help — команды, :quit — выход.\n"
            f"preview={'on' if self.preview else 'off'}"
        )
        while True:
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                self.stdout.write("")
                break
            line = (line or "").strip()
            if not line:
                continue
            if line.startswith(":"):
                if not self._handle_colon(line):
                    break
                continue
            self._handle_query(line)

    def _handle_colon(self, line):
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in (":quit", ":q"):
            return False
        if cmd == ":help":
            self.stdout.write(
                ":help :quit/:q :raw :json :reload :benchmark\n"
                ":preview on/off :verbose :quiet :history :repeat N"
            )
            return True
        if cmd == ":raw":
            raw = (self.last_result or {}).get("raw")
            self.stdout.write(json.dumps(raw, ensure_ascii=False, indent=2))
            return True
        if cmd == ":json":
            self.stdout.write(
                json.dumps(self.last_event or {}, ensure_ascii=False, indent=2)
            )
            return True
        if cmd == ":reload":
            from dict.ai.query_prompts import reference_data_for_parse

            fields, tags = reference_data_for_parse()
            self.stdout.write(f"reloaded: fields={len(fields)} tags={len(tags)}")
            return True
        if cmd == ":benchmark":
            self._run_benchmark()
            return True
        if cmd == ":preview":
            if arg.lower() in ("on", "1", "true"):
                self.preview = True
            elif arg.lower() in ("off", "0", "false"):
                self.preview = False
            else:
                self.stdout.write("usage: :preview on|off")
                return True
            self.stdout.write(f"preview={'on' if self.preview else 'off'}")
            return True
        if cmd == ":verbose":
            self.verbose = True
            self.quiet = False
            self.stdout.write("verbose on")
            return True
        if cmd == ":quiet":
            self.quiet = True
            self.verbose = False
            self.stdout.write("quiet on")
            return True
        if cmd == ":history":
            if not self.history:
                self.stdout.write("(пусто)")
            for i, q in enumerate(self.history, 1):
                self.stdout.write(f"{i}. {q}")
            return True
        if cmd == ":repeat":
            try:
                n = int(arg)
            except ValueError:
                self.stdout.write("usage: :repeat N")
                return True
            if n < 1 or n > len(self.history):
                self.stdout.write("нет такого номера в history")
                return True
            self._handle_query(self.history[n - 1])
            return True

        self.stdout.write(f"неизвестная команда: {cmd}")
        return True

    def _handle_query(self, query):
        self.history.append(query)
        result = parse_query(query)
        groups = None
        fallback_count = None

        if self.preview or not result.get("parse_ok") or not result.get("ok"):
            groups, fallback_count = self._retrieval(result)

        self.last_result = result
        self.last_groups = groups
        self.last_fallback_count = fallback_count
        event = serialize_ai_search_event(
            result, groups=groups, fallback_count=fallback_count
        )
        self.last_event = event
        self._append_log(event)
        self._print_result(result, groups, fallback_count)

    def _retrieval(self, result):
        from dict.ai.search import search_by_parsed

        return search_by_parsed(result)

    def _print_result(self, result, groups, fallback_count):
        display = result.get("display") or "(нет display)"
        meta = result.get("meta") or {}
        latency = meta.get("latency_ms")

        if self.quiet:
            self.stdout.write(display)
            if groups is not None:
                total = sum(g.get("total", 0) for g in groups)
                self.stdout.write(f"groups={len(groups)} hits={total}")
            if fallback_count is not None:
                self.stdout.write(f"fallback={fallback_count}")
            return

        self.stdout.write("--- parse ---")
        self.stdout.write(display)
        self.stdout.write(
            f"lexical={result.get('lexical')}  focus={result.get('focus')}  "
            f"related={result.get('related')}  "
            f"fields={result.get('fields')}  tags={result.get('tags')}  "
            f"place={result.get('place')}  dialect={result.get('dialect')}"
        )
        self.stdout.write(f"dropped={result.get('dropped')}")
        if latency is not None:
            self.stdout.write(f"latency_ms={latency}")

        if not self.quiet:
            self.stdout.write("--- debug ---")
            self.stdout.write(
                f"ok={result.get('ok')} parse_ok={result.get('parse_ok')} "
                f"error={result.get('error')} model={meta.get('model')} "
                f"prompt={meta.get('prompt_version')}"
            )
            warnings = result.get("warnings") or []
            if warnings:
                self.stdout.write(f"warnings={warnings}")
            if self.verbose and result.get("raw") is not None:
                raw_s = json.dumps(result["raw"], ensure_ascii=False)
                if len(raw_s) > 400:
                    raw_s = raw_s[:400] + "…"
                self.stdout.write(f"raw={raw_s}")

        if groups is not None and (self.preview or groups):
            self.stdout.write("--- retrieval ---")
            for g in groups:
                words = ", ".join(
                    a.get("word", "") for a in (g.get("articles") or [])[:5]
                )
                self.stdout.write(
                    f"[{g.get('kind')}] {g.get('title')}  "
                    f"total={g.get('total')}  {words}"
                )

        if fallback_count is not None and (
            not result.get("ok")
            or not result.get("parse_ok")
            or (groups is not None and not groups)
        ):
            self.stdout.write("--- fallback ---")
            self.stdout.write(f"lexical /search/ would find ≈ {fallback_count}")

    def _append_log(self, event):
        if not self.log_path:
            return
        path = Path(self.log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _run_benchmark(self):
        if not BENCHMARKS_PATH.is_file():
            self.stdout.write(
                self.style.ERROR(f"нет файла эталонов: {BENCHMARKS_PATH}")
            )
            return
        from dict.ai.search import run_benchmarks

        cases = json.loads(BENCHMARKS_PATH.read_text(encoding="utf-8"))
        results = run_benchmarks(cases, parse_fn=parse_query)
        ok_n = sum(1 for r in results if r["ok"])
        for r in results:
            mark = "✓" if r["ok"] else "✗"
            detail = f"  {r['detail']}" if r.get("detail") else ""
            self.stdout.write(f"{mark} {r['query']}{detail}")
        self.stdout.write(f"{ok_n}/{len(results)} passed")
        if ok_n < len(results):
            sys.exit(1)
