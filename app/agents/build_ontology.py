#!/usr/bin/env python3
"""
Пилот: построение онтологии смысловых полей по выборке статей через DeepSeek.

Механика (как обсуждали):
- идём по выборке статей;
- вход модели ТОЛЬКО русский: переводы (rus_word) + пометы с расшифровкой
  (Tag.name) + грубо вытащенная кириллица из article_html (хвосты иллюстраций);
  карельский НЕ передаём;
- накапливаем ОБОБЩЕНИЕ: растущий список категорий. В промпт кладём текущий
  список; модель обязана сперва укладывать в существующие, новую заводить
  только если ничего не подходит; "нет смыслового поля" — валидный ответ
  (для союзов/наречий вроде da);
- пометы типов 3/5 — это уже готовые смысловые поля лексикографа, ими и
  засеваем список категорий на старте (каркас, а не чистый лист).

Это ПИЛОТ: цель — проверить, выходит ли согласованная онтология, а не
построить финал. Второй проход ("усушка"/обобщение дублей) — отдельно, после
оценки результата глазами.

Запуск (в окружении с доступом к api.deepseek.com и DEEPSEEK_API_KEY):
    python build_ontology.py --limit 300 --out ontology_pilot.json
Требует: pip install openai ; django настроен (скрипт делает django.setup()).
НЕ коммитить результат вслепую — сначала оценить качество.
"""

import argparse
import json
import os
import re
import sys
import time

# --- окружение: как в probe_deepseek.py (load_env сам находит .env рядом) ---
from load_env import load_env  # noqa: E402

load_env()

# --- все json — в единой папке data/ (рабочий каталог: app/agents) ---
DATA_DIR = "data"


def data_path(name):
    """Путь внутри data/. Абсолютные пути и уже-в-data оставляем как есть."""
    import os as _os
    if _os.path.isabs(name) or name.startswith(DATA_DIR + _os.sep) or name.startswith(DATA_DIR + "/"):
        return name
    _os.makedirs(DATA_DIR, exist_ok=True)
    return _os.path.join(DATA_DIR, name)

# --- Django bootstrap ---
# рабочий каталог запуска — app/agents; проект (punzh, dict) лежит в /app,
# поэтому добавляем РОДИТЕЛЬСКИЙ каталог в путь, затем поднимаем Django.
_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.dirname(_HERE)  # /app
if _APP not in sys.path:
    sys.path.insert(0, _APP)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "punzh.settings")

import django  # noqa: E402

django.setup()

from openai import OpenAI  # noqa: E402
from dict.ai.prompts import (  # noqa: E402
    SYSTEM_PROMPT_FROZEN,
    build_article_input,
    build_user_prompt,
)
from dict.models import (  # noqa: E402
    Article,
    ArticleIndexTranslate,
    ArticleIndexTag,
    Tag,
)


SYSTEM_PROMPT = (
    "Ты классифицируешь словарную статью по смысловым полям. "
    "На вход — РУССКИЕ данные одной статьи: переводы и русские фрагменты "
    "иллюстраций. Твоя задача:\n"
    "1) выделить ключевые слова (по-русски);\n"
    "2) отнести статью к смысловым полям СТРОГО из предложенного списка "
    "категорий; заводи НОВУЮ категорию только если ни одна не подходит;\n"
    "3) если статья не имеет предметно-смыслового поля (служебное слово, "
    "союз, частица, абстрактное наречие) — верни пустой список полей и "
    "\"no_field\": true.\n"
    "Отвечай СТРОГО одним JSON-объектом без пояснений и без markdown:\n"
    '{"keywords": [..], "fields": [..], "new_field": null|"...", '
    '"no_field": false}'
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


# --- служебные части речи, исключаемые из выборки для ПРОЕКТИРОВАНИЯ ---
# (не несут смыслового поля; матчим по подстроке в Tag.name)
SERVICE_POS_KEYWORDS = ["союз", "частица", "предлог", "послелог", "междомети"]


def service_tag_ids():
    """id помет служебных частей речи (по подстроке в name)."""
    ids = set()
    for kw in SERVICE_POS_KEYWORDS:
        for tid in Tag.objects.filter(name__icontains=kw).values_list("id", flat=True):
            ids.add(tid)
    return ids


def sample_significant_translations(n, exclude_article_ids, service_ids):
    """
    Вернуть до n переводов значимой лексики (rus_word), ИСКЛЮЧАЯ статьи:
    - уже использованные (exclude_article_ids) — аккумуляция между прогонами;
    - имеющие служебную помету части речи (service_ids).
    Возвращает (translations, used_article_ids).
    """
    # статьи со служебной пометой — исключаем
    service_articles = set(
        ArticleIndexTag.objects.filter(tag_id__in=service_ids)
        .values_list("article_id", flat=True)
    )
    excluded = set(exclude_article_ids) | service_articles

    # случайные статьи, у которых есть перевод, не в excluded
    qs = (
        Article.objects.exclude(id__in=excluded)
        .filter(articleindextranslate__isnull=False)
        .distinct()
        .order_by("?")
        .values_list("id", flat=True)[: n * 2]  # запас, часть отсеем
    )
    picked = []
    used = []
    for aid in qs:
        trs = list(
            ArticleIndexTranslate.objects.filter(article_id=aid)
            .exclude(rus_word__isnull=True)
            .values_list("rus_word", flat=True)
        )
        if not trs:
            continue
        picked.append(", ".join(trs[:5]))  # компактно: до 5 переводов на статью
        used.append(aid)
        if len(picked) >= n:
            break
    return picked, used


ONTOLOGY_SYSTEM = (
    "Ты проектируешь ОНТОЛОГИЮ СМЫСЛОВЫХ ПОЛЕЙ для диалектного словаря "
    "тверских карелов (сельский говор XIX-XX вв.).\n"
    "ЖЁСТКИЙ КОРИДОР: ровно 25-30 полей, НЕ больше 30. Если насчитал больше — "
    "ОБЪЕДИНЯЙ близкие, пока не станет <=30.\n"
    "Каждое поле — ШИРОКОЕ, покрывает десятки слов. ЗАПРЕЩЕНЫ узкие микрополя "
    "под отдельное действие/предмет/оттенок. Обобщай их в широкие. Примеры "
    "ЗАПРЕЩЁННОГО дробления и куда обобщать:\n"
    "  'удушье','прогрызание','раскалывание','кипячение' -> 'Физические действия и воздействия';\n"
    "  'производство масла','обработка зерна','плетение' -> 'Труд и ремёсла';\n"
    "  'покрытие листвой','укоренение','типы почвы' -> 'Земледелие и растения';\n"
    "  'молодые животные','части тела животных' -> 'Животный мир';\n"
    "  'звуки при еде','медленное питьё' -> 'Пища и напитки' или 'Речь и звуки';\n"
    "  'состояние неба','осадки' -> 'Погода и природа'.\n"
    "НЕ создавай поле под служебные слова. НЕ создавай функционально-"
    "грамматические поля (интенсивность, модальность, причинность, "
    "собирательность, сравнение) — это не смысл.\n"
    "Поля должны покрывать И специальную лексику (растения, животные, "
    "ткачество, земледелие, жилище), И общеупотребительную (действия, "
    "движение, тело и состояния, эмоции, речь, восприятие, пространство, "
    "время, количество).\n"
    "САМОПРОВЕРКА перед ответом: если полей >30 — объедини. "
    "Отвечай СТРОГО одним JSON-массивом без markdown: "
    '[{"field": "название", "definition": "краткое определение"}].'
)


def design_ontology(client, model, sample_translations):
    """Фаза 1: один запрос — модель проектирует список смысловых полей."""
    user = (
        "Примеры переводов из словаря (ориентир по лексике):\n"
        + json.dumps(sample_translations, ensure_ascii=False)
        + "\n\nСпроектируй список смысловых полей."
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": ONTOLOGY_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0,
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        raise ValueError("Фаза 1: не удалось распарсить список полей:\n" + text)
    fields = json.loads(m.group())
    return fields  # [{"field","definition"}]


CONSOLIDATE_SYSTEM = (
    "Тебе даны НЕСКОЛЬКО вариантов онтологии смысловых полей (из разных "
    "прогонов на разных выборках одного диалектного словаря тверских карелов). "
    "Своди их в ОДИН согласованный список. Правила:\n"
    "1) ОБЪЕДИНЯЙ поля-синонимы и расщеплённые близкие. Примеры того, что это "
    "ОДНО поле: 'Речь и звуки' = 'Звуки и речь' = 'Речь и коммуникация' = "
    "'Действия с информацией' -> одно 'Речь и звуки'; 'Семья и родство' + "
    "'Социальные отношения' -> одно 'Социум и родство'; 'Погода и природа' + "
    "'Природа и ландшафт' + 'Погода и время года' -> одно 'Природа и погода'; "
    "'Человек и его тело' + 'Тело и физические состояния' + 'Здоровье и "
    "болезнь' -> одно 'Человек и тело'.\n"
    "2) ЖЁСТКО ИСКЛЮЧИ функционально-грамматические и оценочно-модальные поля "
    "(они НЕ смысловые, это грамматика). Обязательно убери, даже если они "
    "встречаются во многих вариантах: 'Интенсивность и степень', 'Оценка и "
    "качество', 'Оценка и норма', 'Причина и следствие', 'Сравнение и "
    "подобие', 'Абстрактные понятия', 'Судьба и удача', 'Судьба и "
    "случайность', 'Количество и мера' — оставь только если это реально о "
    "предметном смысле, иначе выброси.\n"
    "3) единичные редкие узкие поля из одного варианта — влей в близкое широкое "
    "или отбрось.\n"
    "4) итог — 20-28 ШИРОКИХ смысловых полей.\n"
    "5) для каждого поля дай единое чистое определение.\n"
    "Отвечай СТРОГО одним JSON-массивом без markdown: "
    '[{"field": "название", "definition": "определение"}].'
)


def consolidate_ontologies(client, model, designs):
    """Усушка: свести несколько наборов полей в один. designs — список списков."""
    variants = []
    for i, d in enumerate(designs, 1):
        variants.append(f"Вариант {i}:\n" + json.dumps(d, ensure_ascii=False))
    user = "\n\n".join(variants) + "\n\nСведи в один список."
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": CONSOLIDATE_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0,
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        raise ValueError("Усушка: не распарсить:\n" + text)
    return json.loads(m.group())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--out", default="ontology_out.json")
    # режим 1: проектирование онтологии N прогонами
    ap.add_argument("--design-only", action="store_true",
                    help="только проектировать онтологию (фаза 1), без классификации")
    ap.add_argument("--runs", type=int, default=10,
                    help="сколько прогонов проектирования (для --design-only)")
    ap.add_argument("--sample", type=int, default=80,
                    help="сколько переводов на один прогон проектирования")
    # режим 2: усушка нескольких наборов в один
    ap.add_argument("--consolidate", metavar="DESIGNS_JSON",
                    help="свести наборы полей из файла (выход --design-only) в один")
    # режим 3: классификация по ЗАМОРОЖЕННОЙ онтологии
    ap.add_argument("--ontology", metavar="ONTOLOGY_JSON",
                    help="классифицировать по готовой онтологии из файла")
    ap.add_argument("--limit", type=int, default=300,
                    help="сколько статей классифицировать (режим 3)")
    ap.add_argument("--order", default="random", choices=["random", "id"])
    args = ap.parse_args()

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("DEEPSEEK_API_KEY не установлен", file=sys.stderr)
        sys.exit(1)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")

    # ---------- режим 2: усушка ----------
    if args.consolidate:
        designs = json.load(open(data_path(args.consolidate), encoding="utf-8"))["designs"]
        final = consolidate_ontologies(client, args.model, designs)
        with open(data_path(args.out), "w", encoding="utf-8") as f:
            json.dump({"ontology": final}, f, ensure_ascii=False, indent=2)
        print(f"Усушка: {len(designs)} наборов -> {len(final)} полей. -> {args.out}")
        for o in final:
            print(f"    - {o['field']}: {o.get('definition','')}")
        return

    # ---------- режим 1: проектирование N прогонами с аккумуляцией ----------
    if args.design_only:
        service_ids = service_tag_ids()
        print(f"Служебных помет исключено: {len(service_ids)}")
        used = set()
        designs = []
        for run in range(1, args.runs + 1):
            sample, used_ids = sample_significant_translations(
                args.sample, used, service_ids
            )
            used.update(used_ids)
            ontology = design_ontology(client, args.model, sample)
            designs.append(ontology)
            print(f"Прогон {run}/{args.runs}: полей {len(ontology)} "
                  f"(выборка {len(sample)}, всего использовано {len(used)})")
            time.sleep(0.3)
        with open(data_path(args.out), "w", encoding="utf-8") as f:
            json.dump({"designs": designs, "meta": {
                "runs": args.runs, "sample": args.sample, "model": args.model,
                "total_articles_used": len(used),
            }}, f, ensure_ascii=False, indent=2)
        print(f"\nГотово: {args.runs} наборов сохранено -> {args.out}")
        print("Дальше: --consolidate этим файлом для усушки в единую онтологию.")
        return

    # ---------- режим 3: классификация по замороженной онтологии ----------
    frozen = bool(args.ontology)
    if args.ontology:
        onto = json.load(open(data_path(args.ontology), encoding="utf-8"))["ontology"]
        field_defs = {o["field"]: o.get("definition", "") for o in onto}
    else:
        # fallback: спроектировать на лету (старое поведение, один прогон)
        service_ids = service_tag_ids()
        sample, _ = sample_significant_translations(args.sample, set(), service_ids)
        onto = design_ontology(client, args.model, sample)
        field_defs = {o["field"]: o.get("definition", "") for o in onto}
    categories = set(field_defs.keys())
    print(f"Онтология: {len(categories)} полей")

    # автодокат: если выходной файл уже есть — продолжаем с остатка
    out_path = data_path(args.out)
    assignments = {}
    keywords_all = {}
    no_field_ids = []
    errors = []
    done_ids = set()
    if os.path.exists(out_path):
        try:
            prev = json.load(open(out_path, encoding="utf-8"))
            assignments = prev.get("assignments", {}) or {}
            keywords_all = prev.get("keywords", {}) or {}
            no_field_ids = prev.get("no_field_ids", []) or []
            errors = prev.get("errors", []) or []
            for k in assignments.keys():
                done_ids.add(int(k))
            for i in no_field_ids:
                done_ids.add(int(i))
            print(f"Автодокат: уже обработано {len(done_ids)} статей, продолжаем.")
        except Exception as e:  # noqa: BLE001
            print(f"Не удалось прочитать прежний {out_path} ({e}); начинаем заново.")

    qs = Article.objects.exclude(id__in=done_ids)
    if args.order == "random":
        qs = qs.order_by("?")
    else:
        qs = qs.order_by("id")
    articles = list(qs[: args.limit])
    print(f"К классификации в этот запуск: {len(articles)}")

    def _flush():
        result = {
            "categories": sorted(categories),
            "field_definitions": field_defs,
            "assignments": assignments,
            "keywords": keywords_all,
            "no_field_ids": no_field_ids,
            "errors": errors,
            "meta": {"limit": args.limit, "order": args.order,
                     "model": args.model, "n_done": len(done_ids)},
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    for i, article in enumerate(articles, 1):
        art_input = build_article_input(article)
        try:
            resp = client.chat.completions.create(
                model=args.model,
                messages=[
                    {"role": "system",
                     "content": SYSTEM_PROMPT_FROZEN if frozen else SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(art_input, field_defs)},
                ],
                temperature=0,
            )
            data = parse_json(resp.choices[0].message.content)
        except Exception as e:  # noqa: BLE001
            errors.append((article.id, str(e)))
            continue
        if data is None:
            errors.append((article.id, "bad_json"))
            continue

        fields = data.get("fields") or []
        # при классификации по ЗАМОРОЖЕННОЙ онтологии новые поля запрещены:
        # оставляем только поля из справочника, new_field игнорируем.
        if frozen:
            fields = [f for f in fields if f in field_defs]
        else:
            new_field = data.get("new_field")
            if new_field:
                categories.add(new_field)
                field_defs.setdefault(new_field, "(добавлено при классификации)")
                fields = list(fields) + [new_field]
        if data.get("no_field"):
            no_field_ids.append(article.id)
        assignments[article.id] = fields
        keywords_all[article.id] = data.get("keywords") or []

        if i % 25 == 0:
            print(f"  {i}/{len(articles)}  полей: {len(categories)}  "
                  f"без поля: {len(no_field_ids)}  ошибок: {len(errors)}")
        if i % 100 == 0:
            _flush()  # периодическое сохранение (автодокат при обрыве)
        time.sleep(0.2)

    _flush()
    print(f"\nГотово. Полей: {len(categories)}. Без поля: {len(no_field_ids)}. "
          f"Ошибок: {len(errors)}. Всего обработано: "
          f"{len(assignments) + len(no_field_ids)}. -> {args.out}")


if __name__ == "__main__":
    main()
