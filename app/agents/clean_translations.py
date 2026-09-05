#!/usr/bin/env python3
"""
LLM-очистка ArticleIndexTranslate (backlog §2).

Dry-run (default): отчёт в data/*.json (results: word / before / after).
--write: снимок индекса + запись в БД (миграция 0027).

Примеры:
  # dry-run (итоговый json: word, before, after + report)
  python clean_translations.py --out clean_prod.json

  # отладка: after_llm / after_llm_review / pos / removed / added
  python clean_translations.py --out x.json --debug --id 8992

  # один проход без ревью
  python clean_translations.py --out x.json --no-review --id 8992

  # сырой текст ответов модели (включает --debug)
  python clean_translations.py --out x.json --save-llm-text --id 8992

  # запись из json (без повторного LLM)
  python clean_translations.py --write --from-json data/clean_prod.json
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
from translation_cleanup import (  # noqa: E402
    SYSTEM_PROMPT_CLEAN_TRANSLATIONS,
    SYSTEM_PROMPT_REVIEW_TRANSLATIONS,
    all_gloss_senses,
    build_cleanup_input,
    build_cleanup_review_user_prompt,
    build_cleanup_user_prompt,
    diff_translations,
    parse_cleanup_json,
    sanitize_cleaned_translations,
)

from dict.models import Article  # noqa: E402
from dict.translation_index_write import apply_from_results  # noqa: E402
from dict.translation_index_write import (
    apply_translations,
    make_batch_id,
    snapshot_translation_index,
)


def _chat_json_translations(client, model, system_prompt, user_prompt):
    """One chat completion → (parsed_list_or_None, raw_text)."""
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    text = resp.choices[0].message.content
    return parse_cleanup_json(text), text


def clean_with_llm(
    client,
    model,
    art_input,
    *,
    save_llm_text=False,
    review=True,
):
    """
    Two-pass LLM cleanup (review optional) + ё→е sanitize.

    Returns (cleaned, meta, err).
    meta: after_llm, after_llm_review (if review); optionally llm_text / llm_text_review.
    """
    raw1, text1 = _chat_json_translations(
        client,
        model,
        SYSTEM_PROMPT_CLEAN_TRANSLATIONS,
        build_cleanup_user_prompt(art_input),
    )
    meta = {"after_llm": raw1}
    if save_llm_text:
        meta["llm_text"] = text1
    if raw1 is None:
        return None, meta, "bad_json"

    draft = raw1
    if review:
        time.sleep(0.15)
        raw2, text2 = _chat_json_translations(
            client,
            model,
            SYSTEM_PROMPT_REVIEW_TRANSLATIONS,
            build_cleanup_review_user_prompt(art_input, draft),
        )
        meta["after_llm_review"] = raw2
        if save_llm_text:
            meta["llm_text_review"] = text2
        if raw2 is None:
            # Keep pass-1 draft rather than aborting the article.
            meta["review_error"] = "bad_json"
        else:
            draft = raw2

    cleaned = sanitize_cleaned_translations(
        draft,
        is_service_word=art_input["is_service_word"],
        gloss_senses=all_gloss_senses(art_input),
        original_translations=art_input["translations"],
        article_html=art_input.get("article_html"),
    )
    if cleaned is None:
        return None, meta, "bad_json"
    return cleaned, meta, None


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
    ap.add_argument(
        "--debug",
        action="store_true",
        help=(
            "В results писать отладку: after_llm / after_llm_review, pos, "
            "removed / added и т.п. По умолчанию только word / before / after."
        ),
    )
    ap.add_argument(
        "--save-llm",
        action="store_true",
        help="Синоним --debug (совместимость).",
    )
    ap.add_argument(
        "--no-save-llm",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    ap.add_argument(
        "--save-llm-text",
        action="store_true",
        help="Сырой llm_text / llm_text_review (включает режим отладки).",
    )
    ap.add_argument(
        "--review",
        action="store_true",
        default=True,
        help="Второй LLM-проход (ревью draft по gloss). По умолчанию вкл.",
    )
    ap.add_argument(
        "--no-review",
        action="store_true",
        help="Только один LLM-проход (без ревью).",
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
    save_llm_text = bool(args.save_llm_text)
    debug = bool(args.debug or args.save_llm or save_llm_text) and not args.no_save_llm
    do_review = args.review and not args.no_review

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
        n_changed = sum(
            1
            for r in results.values()
            if isinstance(r.get("after"), list) and r.get("before") != r.get("after")
        )
        payload = {
            "results": results,
            "errors": errors,
            "report": {
                "articles": len(results),
                "errors": len(errors),
                "changed": n_changed,
                "unchanged": len(results) - n_changed,
            },
            "meta": {
                "dry_run": dry_run,
                "model": args.model,
                "limit": args.limit,
                "order": args.order,
                "words": args.words,
                "ids": args.ids,
                "batch_id": batch_id,
                "debug": debug,
                "save_llm_text": save_llm_text,
                "review": do_review,
            },
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    for i, article in enumerate(articles, 1):
        art_input = build_cleanup_input(article)
        if not art_input["translations"]:
            continue
        try:
            cleaned, llm_meta, err = clean_with_llm(
                client,
                args.model,
                art_input,
                save_llm_text=save_llm_text,
                review=do_review,
            )
        except Exception as e:  # noqa: BLE001
            errors[str(article.id)] = {"word": article.word, "error": str(e)}
            continue
        if err:
            errors[str(article.id)] = {"word": article.word, "error": err}
            if debug and llm_meta:
                results[str(article.id)] = {
                    "word": article.word,
                    "before": art_input["translations"],
                    "after": None,
                    "error": err,
                    "pos": art_input.get("pos"),
                    "pos_tags": art_input["pos_tags"],
                    "is_service_word": art_input["is_service_word"],
                    "after_llm": llm_meta.get("after_llm"),
                    **(
                        {"after_llm_review": llm_meta.get("after_llm_review")}
                        if "after_llm_review" in llm_meta
                        else {}
                    ),
                    **(
                        {"llm_text": llm_meta["llm_text"]}
                        if save_llm_text and llm_meta.get("llm_text") is not None
                        else {}
                    ),
                    **(
                        {"llm_text_review": llm_meta["llm_text_review"]}
                        if save_llm_text and llm_meta.get("llm_text_review") is not None
                        else {}
                    ),
                    **(
                        {"review_error": llm_meta["review_error"]}
                        if llm_meta.get("review_error")
                        else {}
                    ),
                }
            continue
        before = art_input["translations"]
        entry = {
            "word": article.word,
            "before": before,
            "after": cleaned,
        }
        if debug:
            entry.update(diff_translations(before, cleaned))
            entry["pos"] = art_input.get("pos")
            entry["pos_tags"] = art_input["pos_tags"]
            entry["is_service_word"] = art_input["is_service_word"]
            entry["after_llm"] = llm_meta.get("after_llm")
            if "after_llm_review" in llm_meta:
                entry["after_llm_review"] = llm_meta.get("after_llm_review")
            if llm_meta.get("review_error"):
                entry["review_error"] = llm_meta["review_error"]
            if save_llm_text and llm_meta.get("llm_text") is not None:
                entry["llm_text"] = llm_meta["llm_text"]
            if save_llm_text and llm_meta.get("llm_text_review") is not None:
                entry["llm_text_review"] = llm_meta["llm_text_review"]
        results[str(article.id)] = entry
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
    rep = {
        "articles": len(results),
        "errors": len(errors),
        "changed": sum(
            1
            for r in results.values()
            if isinstance(r.get("after"), list) and r.get("before") != r.get("after")
        ),
    }
    msg = (
        f"\nГотово. Статей: {rep['articles']}. Изменено: {rep['changed']}. "
        f"Ошибок: {rep['errors']}. -> {out_path}"
    )
    if batch_id:
        msg += f"  batch_id={batch_id}"
    print(msg)


if __name__ == "__main__":
    main()
