#!/usr/bin/env python3
"""
Compare author pilot labels to LLM baseline (multi-label).

Does not call an LLM. Reads JSONL/JSON from disk.

  docker exec --user 1000:1000 -w /app/agents punzh_django \\
    python score_pilot.py \\
      --labels /path/to/labels-pilot-author.jsonl \\
      --baseline /path/to/baseline-llm-pilot.json \\
      --out data/verification/pilot-score.json

Also accepts host paths if files are copied under agents/data/verification/.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

VALID_DECISIONS = {"fields", "no_field", "insufficient"}
VALID_CONF = {"high", "medium", "low"}
VALID_BASIS = {"translation", "examples", "both", "other"}


def load_labels(path: Path) -> dict[int, dict]:
    text = path.read_text(encoding="utf-8").strip()
    rows: list[dict]
    if path.suffix == ".jsonl" or text.startswith("{"):
        rows = []
        for i, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{i}: {e}") from e
    else:
        payload = json.loads(text)
        rows = payload["articles"] if isinstance(payload, dict) else payload

    out: dict[int, dict] = {}
    for row in rows:
        aid = int(row["article_id"])
        decision = (row.get("decision") or "").strip()
        fields = row.get("fields") or []
        if isinstance(fields, str):
            fields = [f.strip() for f in fields.split("|") if f.strip()]
        out[aid] = {
            "article_id": aid,
            "word": row.get("word"),
            "decision": decision,
            "fields": list(fields),
            "confidence": (row.get("confidence") or "").strip(),
            "basis": (row.get("basis") or "").strip(),
            "ambiguous": bool(row.get("ambiguous")),
            "comment": row.get("comment") or "",
        }
    return out


def load_baseline(path: Path) -> dict[int, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    articles = payload["articles"] if isinstance(payload, dict) else payload
    out = {}
    for row in articles:
        aid = int(row["article_id"])
        names = [f["name"] for f in row.get("fields") or []]
        out[aid] = {
            "article_id": aid,
            "word": row.get("word"),
            "fields": names,
            "from_translation": {
                f["name"]: f.get("from_translation", False)
                for f in row.get("fields") or []
            },
            "no_field": bool(row.get("no_field")) or not names,
        }
    return out


def load_tsv_labels(path: Path) -> dict[int, dict]:
    import csv

    out: dict[int, dict] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            aid = int(row["article_id"])
            fields_raw = (row.get("fields") or "").strip()
            fields = [f.strip() for f in fields_raw.split("|") if f.strip()]
            amb = (row.get("ambiguous") or "").strip().lower()
            out[aid] = {
                "article_id": aid,
                "word": row.get("word"),
                "decision": (row.get("decision") or "").strip(),
                "fields": fields,
                "confidence": (row.get("confidence") or "").strip(),
                "basis": (row.get("basis") or "").strip(),
                "ambiguous": amb in {"1", "true", "yes", "да"},
                "comment": row.get("comment") or "",
            }
    return out


def validate_labels(labels: dict[int, dict], field_names: set[str]) -> list[str]:
    errs = []
    for aid, row in sorted(labels.items()):
        d = row["decision"]
        if not d:
            errs.append(f"{aid}: empty decision (not annotated yet)")
            continue
        if d not in VALID_DECISIONS:
            errs.append(f"{aid}: bad decision {d!r}")
        if d == "fields":
            if not row["fields"]:
                errs.append(f"{aid}: decision=fields but fields empty")
            if len(row["fields"]) > 3:
                errs.append(f"{aid}: more than 3 fields")
            for name in row["fields"]:
                if name not in field_names:
                    errs.append(f"{aid}: unknown field {name!r}")
        else:
            if row["fields"]:
                errs.append(f"{aid}: {d} must have empty fields")
        if row["confidence"] and row["confidence"] not in VALID_CONF:
            errs.append(f"{aid}: bad confidence {row['confidence']!r}")
        if row["basis"] and row["basis"] not in VALID_BASIS:
            errs.append(f"{aid}: bad basis {row['basis']!r}")
    return errs


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {
        "precision": round(p, 4),
        "recall": round(r, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def score(labels: dict[int, dict], baseline: dict[int, dict]) -> dict:
    # Only articles with decision=fields or no_field enter classifier metrics.
    # insufficient → catalogue-adequacy bucket, not model error.
    micro_tp = micro_fp = micro_fn = 0
    per_field = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    per_article = []
    skipped_insufficient = []
    incomplete = []

    for aid, lab in sorted(labels.items()):
        if not lab["decision"]:
            incomplete.append(aid)
            continue
        if lab["decision"] == "insufficient":
            skipped_insufficient.append(aid)
            continue
        base = baseline.get(aid)
        if not base:
            raise SystemExit(f"missing baseline for article_id={aid}")

        gold = set(lab["fields"]) if lab["decision"] == "fields" else set()
        pred = set(base["fields"])
        tp_s = gold & pred
        fp_s = pred - gold
        fn_s = gold - pred
        micro_tp += len(tp_s)
        micro_fp += len(fp_s)
        micro_fn += len(fn_s)
        for name in tp_s:
            per_field[name]["tp"] += 1
        for name in fp_s:
            per_field[name]["fp"] += 1
        for name in fn_s:
            per_field[name]["fn"] += 1

        per_article.append(
            {
                "article_id": aid,
                "word": lab.get("word") or base.get("word"),
                "gold": sorted(gold),
                "pred": sorted(pred),
                "jaccard": round(jaccard(gold, pred), 4),
                "extra": sorted(fp_s),
                "missing": sorted(fn_s),
                "exact_match": gold == pred,
            }
        )

    field_scores = {
        name: prf(v["tp"], v["fp"], v["fn"]) for name, v in sorted(per_field.items())
    }
    if field_scores:
        macro_f1 = sum(v["f1"] for v in field_scores.values()) / len(field_scores)
    else:
        macro_f1 = 0.0

    jac_vals = [a["jaccard"] for a in per_article]
    return {
        "n_labeled_scored": len(per_article),
        "n_incomplete": len(incomplete),
        "n_insufficient": len(skipped_insufficient),
        "incomplete_ids": incomplete,
        "insufficient_ids": skipped_insufficient,
        "micro": prf(micro_tp, micro_fp, micro_fn),
        "macro_f1": round(macro_f1, 4),
        "mean_jaccard": round(sum(jac_vals) / len(jac_vals), 4) if jac_vals else None,
        "exact_match_rate": (
            round(sum(1 for a in per_article if a["exact_match"]) / len(per_article), 4)
            if per_article
            else None
        ),
        "per_field": field_scores,
        "per_article": per_article,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", required=True, help="Author labels .jsonl or .tsv")
    ap.add_argument("--baseline", required=True, help="baseline-llm-pilot.json")
    ap.add_argument(
        "--fields",
        default="",
        help="Optional snapshot-*.json to validate field names",
    )
    ap.add_argument("--out", default="", help="Write full score JSON here")
    ap.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Score only filled rows; do not exit on empty decisions",
    )
    args = ap.parse_args()

    labels_path = Path(args.labels)
    if labels_path.suffix == ".tsv":
        labels = load_tsv_labels(labels_path)
    else:
        labels = load_labels(labels_path)
    baseline = load_baseline(Path(args.baseline))

    field_names: set[str] = set()
    if args.fields:
        snap = json.loads(Path(args.fields).read_text(encoding="utf-8"))
        field_names = {f["name"] for f in snap.get("fields", [])}
    else:
        for b in baseline.values():
            field_names.update(b["fields"])

    errs = validate_labels(labels, field_names)
    hard = [e for e in errs if "not annotated yet" not in e]
    incomplete_errs = [e for e in errs if "not annotated yet" in e]
    if hard:
        print("VALIDATION ERRORS:", file=sys.stderr)
        for e in hard:
            print(" ", e, file=sys.stderr)
        raise SystemExit(1)
    if incomplete_errs and not args.allow_incomplete:
        print(
            f"{len(incomplete_errs)} articles not annotated yet; "
            "pass --allow-incomplete to score partial set",
            file=sys.stderr,
        )
        raise SystemExit(2)

    result = score(labels, baseline)
    summary = {
        k: result[k]
        for k in (
            "n_labeled_scored",
            "n_incomplete",
            "n_insufficient",
            "micro",
            "macro_f1",
            "mean_jaccard",
            "exact_match_rate",
        )
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
