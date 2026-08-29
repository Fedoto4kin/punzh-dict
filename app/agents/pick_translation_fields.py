#!/usr/bin/env python3
"""
Пометить уже проставленные смысловые поля: из перевода леммы или нет.

Не переклассифицирует. Иллюстрации в промпт не идут — только переводы
и закрытый список полей статьи (имя + определение).

0 полей — пропуск. Иначе DeepSeek: какие поля из списка относятся к
переводам (можно несколько, можно ни одного). Одно поле тоже спрашиваем:
оно могло прийти из примера.

Заливка в БД — management-команда load_translation_fields, не здесь.

Боевой прогон — после очистки переводов (backlog §2, затем §4).
"""

import argparse
import json
import os
import re
import sys
import time

from load_env import load_env  # noqa: E402

load_env()

DATA_DIR = "data"


def data_path(name):
    """Путь внутри data/. Абсолютные пути и уже-в-data оставляем как есть."""
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

from dict.models import Article  # noqa: E402
from dict.ai.prompts import (  # noqa: E402
    SYSTEM_PROMPT_TRANSLATION_FIELDS,
    build_translation_fields_user_prompt,
    parse_translation_fields,
    translations_for_classification,
)


def parse_json(text):
    """Устойчивый парсинг: срезаем markdown-обёртки, берём первый {...}."""
    t = text.strip()
    t = re.sub(r"^```(json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


def field_payload(assignments):
    seen = []
    names = []
    for a in assignments:
        name = a.field.name
        if name in names:
            continue
        names.append(name)
        seen.append({"field": name, "definition": a.field.definition or ""})
    return seen, names


def build_user_prompt(translations, field_names, field_defs):
    return build_translation_fields_user_prompt(translations, field_names, field_defs)


def pick_with_llm(client, model, translations, field_names, field_defs, allowed_names):
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_TRANSLATION_FIELDS},
            {
                "role": "user",
                "content": build_user_prompt(translations, field_names, field_defs),
            },
        ],
        temperature=0,
    )
    data = parse_json(resp.choices[0].message.content)
    if not data:
        return None, "bad_json"
    chosen = parse_translation_fields(data, allowed_names)
    if chosen is None:
        return None, "bad_json"
    return chosen, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--out", default="translation_fields.json")
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="сколько статей обработать (0 = все с хотя бы одним полем)",
    )
    ap.add_argument("--order", default="id", choices=["random", "id"])
    args = ap.parse_args()

    out_path = data_path(args.out)
    from_translation = {}
    errors = []
    done_ids = set()
    if os.path.exists(out_path):
        try:
            prev = json.load(open(out_path, encoding="utf-8"))
            from_translation = prev.get("from_translation") or {}
            errors = prev.get("errors") or []
            for k in from_translation.keys():
                done_ids.add(int(k))
            print(
                f"Автодокат: уже обработано {len(done_ids)} статей, продолжаем."
            )
        except Exception as e:  # noqa: BLE001
            print(f"Не удалось прочитать прежний {out_path} ({e}); начинаем заново.")
            from_translation = {}
            errors = []
            done_ids = set()

    qs = (
        Article.objects.filter(semantic_assignments__isnull=False)
        .exclude(id__in=done_ids)
        .distinct()
        .prefetch_related(
            "semantic_assignments__field",
            "articleindextranslate_set",
        )
    )
    if args.order == "random":
        qs = qs.order_by("?")
    else:
        qs = qs.order_by("id")
    if args.limit:
        articles = list(qs[: args.limit])
    else:
        articles = list(qs)
    print(f"К разметке «по переводу» в этот запуск: {len(articles)}")

    if not articles:
        print("Нечего обрабатывать.")
        return

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("DEEPSEEK_API_KEY не установлен", file=sys.stderr)
        sys.exit(1)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")

    def _flush():
        result = {
            "from_translation": from_translation,
            "errors": errors,
            "meta": {
                "limit": args.limit,
                "order": args.order,
                "model": args.model,
                "n_done": len(from_translation),
            },
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    n_empty = 0
    for i, article in enumerate(articles, 1):
        assignments = list(article.semantic_assignments.all())
        fields, names = field_payload(assignments)
        if not names:
            continue
        field_defs = {item["field"]: item["definition"] for item in fields}
        translations = translations_for_classification(article)
        try:
            chosen, err = pick_with_llm(
                client, args.model, translations, names, field_defs, set(names)
            )
        except Exception as e:  # noqa: BLE001
            errors.append((article.id, str(e)))
            continue
        if err:
            errors.append((article.id, err))
            continue
        from_translation[str(article.id)] = chosen
        if not chosen:
            n_empty += 1
        time.sleep(0.2)

        if i % 25 == 0:
            print(
                f"  {i}/{len(articles)}  готово: {len(from_translation)}  "
                f"без полей из перевода: {n_empty}  ошибок: {len(errors)}"
            )
        if i % 100 == 0:
            _flush()

    _flush()
    print(
        f"\nГотово. Статей: {len(from_translation)}. "
        f"Без полей из перевода: {n_empty}. Ошибок: {len(errors)}. "
        f"-> {out_path}"
    )


if __name__ == "__main__":
    main()
