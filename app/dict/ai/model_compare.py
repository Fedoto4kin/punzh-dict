"""
Score query-parse models against ai_query_benchmarks.json.

Live gateway calls stay in manage.py compare_ai_models.
"""

# Timeweb AI Gateway ids (panel catalog, 2026-10-24).
CANDIDATE_MODELS = (
    "zai/glm-4.7-flashx",
    "anthropic/claude-haiku-5-5",
    "dashscope/qwen3.5-flash",
    "xiaomi/mimo-v2.6-flash",
)

# Examples linked from the empty /ai-search/ state.
PAGE_EXAMPLE_QUERIES = (
    "чем режут хлеб",
    "приметы про животных",
    "как варили пиво",
    "весьегонские слова про погоду",
)


def dedupe_models(models):
    out = []
    for model in models:
        if model and model not in out:
            out.append(model)
    return out


def model_roles(model, *, query_model):
    roles = []
    if model == query_model:
        roles.append("разбор сейчас")
    if model in CANDIDATE_MODELS:
        roles.append("дешёвая")
    return roles


def axes_digest(parsed):
    parsed = parsed or {}
    return {
        "ok": bool(parsed.get("ok")),
        "parse_ok": bool(parsed.get("parse_ok")),
        "lexical": list(parsed.get("lexical") or []),
        "focus": list(parsed.get("focus") or []),
        "fields": list(parsed.get("fields") or []),
        "tags": list(parsed.get("tags") or []),
        "dialect": parsed.get("dialect"),
        "dropped": list(parsed.get("dropped") or []),
        "display": parsed.get("display") or "",
    }


def summarize_parse(rows):
    return _summarize(
        rows,
        passed_key="ok",
        extra=lambda items: {
            "failed": [row["query"] for row in items if not row.get("ok")],
        },
    )


def _summarize(rows, *, passed_key, extra):
    grouped = {}
    order = []
    for row in rows:
        model = row["model"]
        if model not in grouped:
            order.append(model)
            grouped[model] = []
        grouped[model].append(row)
    out = []
    for model in order:
        items = grouped[model]
        latencies = [
            row["latency_ms"] for row in items if row.get("latency_ms") is not None
        ]
        summary = {
            "model": model,
            "passed": sum(1 for row in items if row.get(passed_key)),
            "total": len(items),
            "avg_ms": int(sum(latencies) / len(latencies)) if latencies else None,
            "over_prod_timeout": sum(
                1 for row in items if row.get("over_prod_timeout")
            ),
        }
        summary.update(extra(items))
        out.append(summary)
    return out
