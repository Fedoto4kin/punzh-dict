# Данные эксперимента

Сюда кладём срезы и ответы (по умолчанию в git не попадают, см. `.gitignore`).

## Срез фазы 0 (2026-11-02)

| Файл | Содержание |
|------|------------|
| `SNAPSHOT.md` / `snapshot-20261102.json` | Метаданные среза, 28 полей |
| `subject-tags-inventory.json` | Все `Tag` + кандидаты type=3 |
| `subject-tags-whitelist.json` | Предметные пометы → черновые поля |
| `sample-pilot-ids.json` | Пилот: 30 random + 20 target, seed `20261102` |
| `annotator-cards-pilot.jsonl` / `.tsv` | Карточки **без** LLM-полей |
| `baseline-llm-pilot.json` | Текущая БД-разметка (не показывать эксперту до сдачи) |

Пересборка:

```bash
docker exec --user 1000:1000 -w /app/agents punzh_django \
  python verification_export.py --all --out data/verification
cp app/agents/data/verification/* research/classification-verification/data/
```

## Фаза 1 (разметка)

| Файл | Содержание |
|------|------------|
| `annotator-cards-pilot.md` | Читаемый пакет 50 карточек |
| `labels-pilot-author.jsonl` / `.tsv` | Шаблон ответов автора (заполнить) |
| `baseline-llm-pilot.json` | Не смотреть до сдачи |

Метрики: `app/agents/score_pilot.py`.
