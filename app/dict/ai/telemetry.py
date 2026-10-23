"""
Serialize AI search events for JSONL logs (dev REPL) and future AiSearchLog (beta).
"""


def serialize_ai_search_event(parse_result, groups=None, fallback_count=None):
    """One JSON-serializable record; groups/fallback filled in phase B."""
    meta = parse_result.get("meta") or {}
    return {
        "query_raw": parse_result.get("query", ""),
        "parse_ok": parse_result.get("parse_ok", False),
        "ok": parse_result.get("ok", False),
        "error": parse_result.get("error"),
        "display": parse_result.get("display", ""),
        "parsed": {
            "lexical": parse_result.get("lexical", []),
            "related": parse_result.get("related", []),
            "fields": parse_result.get("fields", []),
            "tags": parse_result.get("tags", []),
            "place": parse_result.get("place"),
            "dialect": parse_result.get("dialect"),
            "dropped": parse_result.get("dropped", []),
        },
        "warnings": parse_result.get("warnings", []),
        "raw": parse_result.get("raw"),
        "groups_json": groups or [],
        "fallback_count": fallback_count,
        "model_query": meta.get("model", ""),
        "prompt_version": meta.get("prompt_version", ""),
        "latency_ms": meta.get("latency_ms"),
    }
