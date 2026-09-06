# Аудит индекса переводов

Статус: **план** (код ещё нет). Связанный runbook: `docs/translation_cleanup.md`.

## Введение: как сделаны переводы

Русский поисковый индекс — строки `ArticleIndexTranslate.rus_word` по статьям.
Их приводит в порядок оффлайн LLM (`app/agents/clean_translations.py` +
`translation_cleanup.py`): dual-pass (draft + review, DeepSeek).

- **Dry-run** (default): json в `app/agents/data/` — на статью только
  `word` / `before` / `after`; сверху `report` и `meta`. Отладка — `--debug`.
- **Заливка:** `--write --from-json …` (`dict/translation_index_write.py`).
- **Sanitize** на стабильном контуре минимальный: ё→е, trim, dedupe.
  Фразовая чистка — ответственность промптов; агрессивные пост-хелперы
  (склейка запятых и т.п.) в прод не возвращаем без отдельного решения.
- Ложные разбиения фраз поиск в целом терпит; exact-match и качество
  выдачи от части артефактов страдают — это зона аудита, не «тихой»
  починки в sanitize.

---

## Цель

После prod dry-run / `--write` найти **классы дефектов** индекса read-only
отчётом. Правки — отдельно (restore, ручной CSV, точечный `--id` re-run).

**Не цели:** переписывать промпты; онтология / `from_translation`; полный
ручной просмотр корпуса; LLM внутри аудита.

---

## Источники данных

| Фаза | Вход | Когда |
|------|------|--------|
| **A** | `clean_prod.json` (`before` / `after`, `report`) | после dry-run |
| **B** | текущий индекс + `gloss_senses_from_html` | ongoing QA |

---

## Классы проверок

### 1. Ложное разбиение уточнения после запятой (N) — MVP

В `before`/gloss есть целая фраза `X, Y…`, в `after`/индексе — отдельно `X` и
хвост (`причастие` / `где` / `который` / `для`…).

Примеры: `тряпка` + `намотанная…`; `место` + `где ощущается…`.

### 2. Лишние строки «и …» — MVP

В `added`/индексе есть `и <слово>` без опоры в gloss как отдельного члена
(артефакт вроде «… и пр.»). Пример: `и злодей` при нормальном `злодей`.

### 3. Осколок без вершины

Голый объект / хвост эллипсиса при глагольной лемме; **не** путать с краткими
V-вершинами параллели из gloss.

### 4. Потеря краткой V-вершины

В gloss/before краткий инфинитив-член параллели есть, в after — только
развёрнутые `V + …`.

### 5. Поглощённый headword

Однословник из `before`/gloss пропал, в индексе осталась только многословная
фраза с тем же токеном (`глаз` при `дурной глаз`). Источник — json cleanup,
не таблица снимка.

### 6. Расхождение с gloss (мягко)

Многословная фраза gloss отсутствует в индексе; или строки индекса вне
before/gloss (кандидаты на выдумку). Высокий шум — только сводка / sample.

### 7. (Позже) служебные леммы

`is_service_word` и строки >3 слов / похожие на иллюстрации.

---

## Поставка

```
app/dict/translation_index_audit.py
app/dict/management/commands/audit_translation_index.py
app/dict/tests/test_translation_index_audit.py
```

CLI (эскиз):

```bash
# A: dry-run json
python manage.py audit_translation_index \
  --from-json /app/agents/data/clean_prod.json
python manage.py audit_translation_index \
  --from-json … --check comma_split,and_prefix --csv

# B/C: БД
python manage.py audit_translation_index --from-db
python manage.py audit_translation_index --from-db --batch-id <id>
```

Вывод: сводка по классам + детальный CSV/JSON
(`article_id`, `word`, `check`, `evidence`).

**Инварианты:** только чтение; не писать в индекс; не звать LLM.

---

## Этапы

| # | Что | Результат |
|---|-----|-----------|
| **0** | Этот план + строка в INDEX | ✓ |
| **1** | Парсер json + checks 1–2 на фикстурах | тесты |
| **2** | Прогон на `clean_prod.json` → частоты | политика: чинить / игнор |
| **3** | `--from-db` + json before/after; check 5 = wrap subsumed | post-write QA |
| **4** | Checks 3–4, 6 по мере шума | уточнение правил |
| **5** | Отдельный контур правок (не смешивать с аудитом) | restore / `--id` |

Поток:

```
dry-run json ──► audit A ──► (ок) ──► --write
                    │
                    └── правки / повтор dry-run по --id
--write ──► audit B (индекс + gloss)
```

---

## Критерии готовности MVP

- Команда отчёта по json без записи в БД.
- Checks **comma_split** и **and_prefix** покрыты тестами на примерах пилота.
- Короткий § в `translation_cleanup.md` («Аудит после cleanup») со ссылкой сюда.

---

## Политика (черновик)

- Ложные разбиения N+уточнение: низкий приоритет, если exact не страдает.
- «и …» и потерянные exact-headwords: чинить раньше.
- Sanitize/промпты не раздувать, пока аудит не даст частоты.
