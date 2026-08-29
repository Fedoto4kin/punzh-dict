#!/usr/bin/env python3
"""
LLM-очистка ArticleIndexTranslate (backlog §2).

Dry-run (default): отчёт в data/*.json.
--write: снимок индекса + запись в БД (миграция 0027).

Примеры:
  # dry-run пилот
  python clean_translations.py --out clean_final_test.json --id 8992

  # запись из json (без повторного LLM)
  python clean_translations.py --write --from-json data/clean_final_test.json

  # полный прогон с LLM и записью
  python clean_translations.py --write --out clean_prod.json
"""

import argparse
import json
import os
import sys
import time

from load_env import load_env  # noqa: E402

load_env()

DATA_DIR = "data"


def data_path(name):
    import os as _os

    if (
        _os.path.isabs(name)
        or name.startswith(DATA_DIR + _os.sep)
        or name.startswith(DATA_DIR + "/")
    ):
        return name
    _os.makedirs(DATA_DIR, exist_ok=True)
    return _os.path.join(DATA_DIR, name)


_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.dirname(_HERE)
if _APP not in sys.path:
    sys.path.insert(0, _APP)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "punzh.settings")

import django  # noqa: E402

django.setup()

from openai import OpenAI  # noqa: E402

from dict.translation_index_write import (  # noqa: E402
    apply_from_results,
    apply_translations,
    make_batch_id,
    snapshot_translation_index,
)
from translation_cleanup import (  # noqa: E402
    SYSTEM_PROMPT_CLEAN_TRANSLATIONS,
    all_gloss_senses,
    build_cleanup_input,
    build_cleanup_user_prompt,
    diff_translations,
    parse_cleanup_json,
    sanitize_cleaned_translations,
)
from dict.models import Article  # noqa: E402


def clean_with_llm(client, model, art_input):
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_CLEAN_TRANSLATIONS},
            {"role": "user", "content": build_cleanup_user_prompt(art_input)},
        ],
        temperature=0,
    )
    raw = parse_cleanup_json(resp.choices[0].message.content)
    if raw is None:
        return None, "bad_json"
    cleaned = sanitize_cleaned_translations(
        raw,
        is_service_word=art_input["is_service_word"],
        gloss_senses=all_gloss_senses(art_input),
        original_translations=art_input["translations"],
    )
    if cleaned is None:
        return None, "bad_json"
    return cleaned, None


def select_articles(args):
    qs = Article.objects.filter(articleindextranslate__isnull=False).distinct()
    if args.ids:
        qs = qs.filter(id__in=args.ids)
    if args.words:
        from django.db.models import Q

        q = Q()
        for w in args.words:
            q |= Q(word__iexact=w)
        qs = qs.filter(q)
    if args.order == "random":
        qs = qs.order_by("?")
    else:
        qs = qs.order_by("id")
    qs = qs.prefetch_related("articleindextranslate_set", "additions")
    if args.limit:
        return list(qs[: args.limit])
    return list(qs)


def main():
    ap = argparse.ArgumentParser(description="LLM cleanup of rus_word index.")
    ap.add_argument(
        "--write",
        action="store_true",
        help="Снимок индекса + запись ArticleIndexTranslate в БД.",
    )
    ap.add_argument(
        "--from-json",
        metavar="PATH",
        help="При --write: применить готовый json (results), без LLM.",
    )
    ap.add_argument(
        "--batch-id",
        help="Имя снимка (по умолчанию cleanup_YYYYMMDDTHHMMSSZ).",
    )
    ap.add_argument(
        "--skip-snapshot",
        action="store_true",
        help="При --write: не создавать снимок (только для повторных тестов).",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Dry-run: перепроцессить id даже если уже в --out json.",
    )
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--out", default="clean_translations.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--order", default="id", choices=["random", "id"])
    ap.add_argument(
        "--word",
        action="append",
        default=[],
        dest="words",
        help="Лемма (можно несколько --word).",
    )
    ap.add_argument(
        "--id",
        type=int,
        action="append",
        default=[],
        dest="ids",
        help="id статьи (можно несколько --id).",
    )
    args = ap.parse_args()

    dry_run = not args.write

    if args.write and args.from_json:
        path = data_path(args.from_json)
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        results = payload.get("results") or {}
        if not results:
            print(f"Нет results в {path}", file=sys.stderr)
            sys.exit(1)
        batch_id = args.batch_id or make_batch_id()
        if not args.skip_snapshot:
            n_snap = snapshot_translation_index(batch_id)
            print(f"Снимок {batch_id}: {n_snap} строк.")
        else:
            print("Снимок пропущен (--skip-snapshot).")
        batch_id, n = apply_from_results(results, batch_id, do_snapshot=False)
        print(f"Записано статей: {n}. batch_id={batch_id}")
        return

    out_path = data_path(args.out)
    results = {}
    errors = {}
    done_ids = set()

    if os.path.exists(out_path) and dry_run and not args.force:
        try:
            prev = json.load(open(out_path, encoding="utf-8"))
            results = prev.get("results") or {}
            errors = prev.get("errors") or {}
            for k in results:
                done_ids.add(int(k))
            if done_ids:
                print(f"Автодокат: в {out_path} уже {len(done_ids)} статей.")
        except Exception as e:  # noqa: BLE001
            print(f"Не читаем {out_path} ({e}); начинаем заново.")

    articles = [a for a in select_articles(args) if a.id not in done_ids]
    print(f"К обработке в этом запуске: {len(articles)} (dry_run={dry_run})")

    if not articles:
        print("Нечего обрабатывать.")
        return

    batch_id = None
    snap_done = False
    if args.write and not args.skip_snapshot:
        batch_id = args.batch_id or make_batch_id()
        n_snap = snapshot_translation_index(batch_id)
        snap_done = True
        print(f"Снимок {batch_id}: {n_snap} строк.")

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("DEEPSEEK_API_KEY не установлен", file=sys.stderr)
        sys.exit(1)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")

    def _flush():
        payload = {
            "results": results,
            "errors": errors,
            "meta": {
                "dry_run": dry_run,
                "model": args.model,
                "limit": args.limit,
                "order": args.order,
                "words": args.words,
                "ids": args.ids,
                "n_done": len(results),
                "batch_id": batch_id,
            },
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    for i, article in enumerate(articles, 1):
        art_input = build_cleanup_input(article)
        if not art_input["translations"]:
            continue
        try:
            cleaned, err = clean_with_llm(client, args.model, art_input)
        except Exception as e:  # noqa: BLE001
            errors[str(article.id)] = str(e)
            continue
        if err:
            errors[str(article.id)] = err
            continue
        before = art_input["translations"]
        results[str(article.id)] = {
            "word": article.word,
            "before": before,
            "after": cleaned,
            **diff_translations(before, cleaned),
            "pos_tags": art_input["pos_tags"],
            "is_service_word": art_input["is_service_word"],
        }
        if args.write:
            if not snap_done and not args.skip_snapshot:
                batch_id = args.batch_id or make_batch_id()
                snapshot_translation_index(batch_id)
                snap_done = True
                print(f"Снимок {batch_id}: создан.")
            apply_translations(article.id, cleaned)
        time.sleep(0.2)

        if i % 5 == 0:
            print(f"  {i}/{len(articles)}  ok={len(results)}  err={len(errors)}")
            _flush()

    _flush()
    msg = f"\nГотово. Статей: {len(results)}. Ошибок: {len(errors)}. -> {out_path}"
    if batch_id:
        msg += f"  batch_id={batch_id}"
    print(msg)


if __name__ == "__main__":
    main()
