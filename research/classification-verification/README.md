# Верификация LLM-классификации диалектной лексики

Продолжение работы по тематической классификации словаря А. В. Пунжиной
(тверские говоры): не повтор разметки, а **независимая оценка качества,
воспроизводимости и границ** автоматической атрибуции по 28 смысловым полям.

**Предшественник:** статья А. А. Федоточкина для Studia Nordica —
`research/studia-nordica/` (черновик / выгрузка). В §8–§9 там прямо указана
систематическая оценка на измеримой выборке как следующий этап.

**Рабочее название:** *Верификация и оценка воспроизводимости LLM-классификации
диалектной лексики на материале электронного словаря карельского языка
(тверские говоры).*

**Источник:** электронный словарь — https://punzhina.krc.karelia.ru/  
Технический контур разметки: `docs/method-onthlogy-markup.md`,
`app/agents/build_ontology.py`, модели `SemanticField` /
`ArticleSemanticField`.

## Файлы

| Файл | Содержание |
|------|------------|
| `research-plan.md` | Исследовательский план: вопросы, фазы, метрики, предостережения |
| `annotator-guidelines.md` | Инструкции экспертной разметки (черновик) |
| `data/` | Срезы выборок, сырые ответы LLM, нормализованная разметка (не коммитить сырьё с ключами; ценные срезы — осознанно) |

## Статус

**Фаза 0 сделана.** **Фаза 1:** разметка автором.

1. Читать карточки: `data/annotator-cards-pilot.md` (+ гайд).
2. Писать ответы в `data/labels-pilot-author.jsonl` или `.tsv`.
3. **Не открывать** `baseline-llm-pilot.json` до сдачи.
4. После сдачи — метрики:

```bash
docker exec --user 1000:1000 -w /app/agents punzh_django \
  python score_pilot.py \
    --labels data/verification/labels-pilot-author.jsonl \
    --baseline data/verification/baseline-llm-pilot.json \
    --fields data/verification/snapshot-20261102.json \
    --out data/verification/pilot-score.json
```

(Скопируйте labels в `app/agents/data/verification/` перед запуском в контейнере.)

Эталон — человеческая разметка; БД-атрибуция LLM **не** gold.
