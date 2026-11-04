"""
Compare the configured AI query-parse model with cheaper gateway models.

Uses the same parse prompt and validation as /ai-search/.
Cases: app/dict/fixtures/custom/ai_query_benchmarks.json (docs + page examples).

    docker exec --user 1000:1000 -w /app punzh_django \
      python manage.py compare_ai_models --list

    docker exec --user 1000:1000 -w /app punzh_django \
      python manage.py compare_ai_models --out /tmp/ai-model-compare.json

Each live call uses a longer timeout than production; over_prod_timeout marks
answers that would miss PARSE_TIMEOUT.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from dict.ai.model_compare import (
    CANDIDATE_MODELS,
    PAGE_EXAMPLE_QUERIES,
    axes_digest,
    dedupe_models,
    model_roles,
    summarize_parse,
)
from dict.ai.query_parse import PARSE_TIMEOUT, parse_query
from dict.ai.search import check_benchmark_case
from dict.management.commands.ai_query import BENCHMARKS_PATH

COMPARE_TIMEOUT = 40


class Command(BaseCommand):
    help = (
        "Сравнить разбор запроса: текущая модель шлюза и дешёвые "
        "GLM 4.7 FlashX, Claude 5.5 Haiku, Qwen 3.5 Flash, MiMo V2.6 Flash."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--list",
            action="store_true",
            help="Показать модели и запросы, без вызовов шлюза.",
        )
        parser.add_argument(
            "--models",
            type=str,
            default="",
            help="Список id через запятую вместо четырёх дешёвых моделей.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=COMPARE_TIMEOUT,
            help=f"Таймаут одного вызова, секунды (по умолчанию {COMPARE_TIMEOUT}).",
        )
        parser.add_argument(
            "--out",
            type=str,
            default="",
            help="Записать полный JSON-отчёт в этот путь.",
        )

    def handle(self, *args, **options):
        cases = json.loads(BENCHMARKS_PATH.read_text(encoding="utf-8"))
        query_model = getattr(settings, "TIMEWEB_AI_MODEL_QUERY", "")
        candidates = _parse_model_list(options["models"]) or list(CANDIDATE_MODELS)
        if options["list"]:
            self._print_list(cases, query_model, candidates)
            return

        timeout = options["timeout"]
        report = {
            "query_model": query_model,
            "candidates": candidates,
            "prod_parse_timeout_s": PARSE_TIMEOUT,
            "call_timeout_s": timeout,
            "parse": None,
        }

        parse_models = dedupe_models([query_model, *candidates])
        parse_rows = []
        for model in parse_models:
            self.stdout.write(f"разбор: {model}")
            for case in cases:
                row = self._parse_case(case, model, timeout)
                parse_rows.append(_without_parsed(row))
                mark = "✓" if row["ok"] else "✗"
                self.stdout.write(f"  {mark} {case['query']}")
        report["parse"] = {
            "summary": summarize_parse(parse_rows),
            "rows": parse_rows,
        }
        self._print_parse_summary(report["parse"]["summary"], query_model)

        out = options["out"]
        if out:
            path = Path(out)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            self.stdout.write(f"отчёт: {path}")

    def _print_list(self, cases, query_model, candidates):
        self.stdout.write(f"разбор сейчас: {query_model}")
        self.stdout.write("кандидаты:")
        for model in candidates:
            self.stdout.write(f"  {model}")
        self.stdout.write(f"эталоны: {len(cases)} ({BENCHMARKS_PATH})")
        queries = {case.get("query") for case in cases}
        missing = [q for q in PAGE_EXAMPLE_QUERIES if q not in queries]
        if missing:
            self.stdout.write(self.style.WARNING("нет примеров со страницы:"))
            for query in missing:
                self.stdout.write(f"  {query}")
        else:
            self.stdout.write("примеры со страницы есть в эталонах.")

    def _parse_case(self, case, model, timeout):
        query = case.get("query") or ""
        started = time.monotonic()
        parsed = parse_query(query, timeout=timeout, model=model)
        latency_ms = int((time.monotonic() - started) * 1000)
        ok, detail = check_benchmark_case(parsed, case)
        return {
            "model": model,
            "query": query,
            "ok": ok,
            "detail": detail,
            "latency_ms": latency_ms,
            "over_prod_timeout": latency_ms > PARSE_TIMEOUT * 1000,
            "parsed": parsed,
            "axes": axes_digest(parsed),
        }

    def _print_parse_summary(self, summary, query_model):
        self.stdout.write("")
        self.stdout.write(
            f"Разбор, порог продакшена {PARSE_TIMEOUT} с "
            "(дольше — колонка «медленно»)."
        )
        self._print_summary_table(summary, query_model, "провалы разбора")

    def _print_summary_table(self, summary, query_model, fail_title):
        for row in summary:
            roles = ", ".join(model_roles(row["model"], query_model=query_model))
            role_s = f" [{roles}]" if roles else ""
            avg = "—" if row["avg_ms"] is None else str(row["avg_ms"])
            self.stdout.write(
                f"{row['passed']}/{row['total']}  {avg} мс  "
                f"медленно {row['over_prod_timeout']}  {row['model']}{role_s}"
            )
            failed = row.get("failed") or []
            if failed:
                self.stdout.write(f"  {fail_title}: {', '.join(failed)}")


def _parse_model_list(raw):
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def _without_parsed(row):
    return {key: value for key, value in row.items() if key != "parsed"}
