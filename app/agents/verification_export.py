#!/usr/bin/env python3
"""
Phase-0 exports for LLM classification verification.

Writes snapshot, tag inventory, annotator cards, LLM baseline, and pilot
sample ids. No LLM calls. Does not write to the DB.

Run (dev):
  docker exec --user 1000:1000 -w /app/agents punzh_django \\
    python verification_export.py --all --out data/verification

Then copy data/verification/* to research/classification-verification/data/
on the host if needed.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import subprocess
import sys
from datetime import date
from pathlib import Path

from load_env import load_env  # noqa: E402

load_env()

DATA_DIR = "data"

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.dirname(_HERE)
if _APP not in sys.path:
    sys.path.insert(0, _APP)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "punzh.settings")

import django  # noqa: E402

django.setup()

from django.db.models import Count, Prefetch  # noqa: E402

from dict.ai.prompts import build_article_input  # noqa: E402
from dict.models import (  # noqa: E402
    Article,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleSemanticField,
    SemanticField,
    Tag,
)

# POS tags used in the Studia Nordica design frame (noun / verb / adjective).
CONTENT_POS_TAGS = ("s", "v", "a")

# Stylistic / register labels under Tag.type=3 — not subject-matter.
STYLISTIC_TYPE3_TAGS = frozenset(
    {
        "арх.",
        "бранн.",
        "груб.",
        "детск.",
        "ирон.",
        "неодобр.",
        "перен.",
        "поэт.",
        "пренебр.",
        "флк.",
        "шутл.",
    }
)

# Draft mapping for phase-4 experiments (not gold).
DEFAULT_SUBJECT_WHITELIST = [
    {
        "tag": "бот.",
        "name": "ботаника",
        "fields": ["Земледелие и растения"],
        "note": "Plant / botanical terms",
    },
    {
        "tag": "зоол.",
        "name": "зоология",
        "fields": ["Животный мир"],
        "note": "Zoological terms",
    },
    {
        "tag": "миф.",
        "name": "мифология",
        "fields": ["Религия и верования"],
        "note": "Mythological beings / lore",
    },
    {
        "tag": "религ.",
        "name": "религиозное",
        "fields": ["Религия и верования"],
        "note": "Religious lexicon",
    },
    {
        "tag": "стр.",
        "name": "строительство",
        "fields": ["Жилище и постройки"],
        "note": "Building / construction; may be rare in index",
    },
    {
        "tag": "с.-х.",
        "name": "сельское хозяйство",
        "fields": ["Сельское хозяйство", "Земледелие и растения"],
        "note": "Agriculture; may overlap plant vs livestock fields",
    },
    {
        "tag": "ткац.",
        "name": "ткацкое дело",
        "fields": ["Труд и ремёсла", "Одежда и ткани"],
        "note": "Weaving craft",
    },
    {
        "tag": "этн.",
        "name": "этнография",
        "fields": ["Социум и родство"],
        "note": "Ethnographic; loose — often culture/custom, not one field",
    },
    {
        "tag": "примета",
        "name": "примета",
        "fields": ["Религия и верования"],
        "note": "Omen / folk belief label; check article before strong claims",
    },
    {
        "tag": "техн.",
        "name": "технический термин",
        "fields": ["Труд и ремёсла", "Материалы и вещества"],
        "note": "Technical term; weak mapping",
    },
]

PILOT_SEED = 20261102
PILOT_RANDOM_N = 30
PILOT_TARGET_N = 20


def out_path(out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / name


def git_rev() -> str | None:
    """Best-effort: container often has no .git (only ./app mounted)."""
    candidates = [Path(_APP).parent, Path(_APP), Path.cwd()]
    for root in candidates:
        try:
            r = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except OSError:
            continue
    return None


def write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {path}")


def dump_snapshot(out_dir: Path, dump_name: str) -> dict:
    fields = []
    for f in SemanticField.objects.order_by("sorting", "name"):
        fields.append(
            {
                "id": f.id,
                "sorting": f.sorting,
                "name": f.name,
                "definition": f.definition or "",
            }
        )
    n_articles = Article.objects.count()
    n_fields = SemanticField.objects.count()
    n_asg = ArticleSemanticField.objects.count()
    n_from_tr = ArticleSemanticField.objects.filter(from_translation=True).count()
    payload = {
        "snapshot_date": "2026-11-02",
        "dump_file": dump_name,
        "source": "prod karielan-hub pg_dump -Fc",
        "git_rev": git_rev(),
        "counts": {
            "articles": n_articles,
            "semantic_fields": n_fields,
            "article_semantic_assignments": n_asg,
            "from_translation_true": n_from_tr,
            "from_translation_share": (
                round(n_from_tr / n_asg, 4) if n_asg else None
            ),
        },
        "fields": fields,
    }
    write_json(out_path(out_dir, "snapshot-20261102.json"), payload)

    md_lines = [
        "# Snapshot 2026-11-02",
        "",
        f"- Dump: `{dump_name}` (prod karielan-hub)",
        f"- Git rev: `{payload['git_rev'] or 'n/a'}`",
        f"- Articles: **{n_articles}**",
        f"- Semantic fields: **{n_fields}**",
        f"- Assignments: **{n_asg}** "
        f"(from_translation={n_from_tr}, "
        f"share={payload['counts']['from_translation_share']})",
        "",
        "## Fields",
        "",
    ]
    for f in fields:
        md_lines.append(f"{f['sorting']}. **{f['name']}** — {f['definition']}")
    md_path = out_path(out_dir, "SNAPSHOT.md")
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"wrote {md_path}")
    return payload


def dump_tag_inventory(out_dir: Path) -> dict:
    rows = []
    for t in Tag.objects.order_by("type", "sorting", "tag"):
        n = ArticleIndexTag.objects.filter(tag=t).count()
        rows.append(
            {
                "id": t.id,
                "tag": t.tag,
                "name": t.name,
                "type": t.type,
                "type_label": dict(Tag.TYPES).get(t.type, str(t.type)),
                "article_count": n,
                "is_stylistic_type3": t.type == 3 and t.tag in STYLISTIC_TYPE3_TAGS,
            }
        )
    inventory = {
        "generated": date.today().isoformat(),
        "note": (
            "Tag.type=3 mixes stylistic and subject labels; "
            "use subject-tags-whitelist.json for subject-matter experiments."
        ),
        "tags": rows,
        "type3_subject_candidates": [
            r
            for r in rows
            if r["type"] == 3 and not r["is_stylistic_type3"]
        ],
    }
    write_json(out_path(out_dir, "subject-tags-inventory.json"), inventory)

    # Enrich whitelist with live ids / counts.
    by_tag = {r["tag"]: r for r in rows}
    whitelist = {
        "generated": date.today().isoformat(),
        "note": (
            "Draft mapping tag → thematic field(s) for phase 4. "
            "Not equivalent systems; absence of a tag ≠ absence of theme."
        ),
        "tags": [],
    }
    for item in DEFAULT_SUBJECT_WHITELIST:
        live = by_tag.get(item["tag"], {})
        whitelist["tags"].append(
            {
                **item,
                "id": live.get("id"),
                "article_count": live.get("article_count", 0),
            }
        )
    write_json(out_path(out_dir, "subject-tags-whitelist.json"), whitelist)
    return inventory


def article_tags_payload(article: Article) -> list[dict]:
    out = []
    for ait in article.articleindextag_set.all():
        t = ait.tag
        out.append(
            {
                "tag": t.tag,
                "name": t.name,
                "type": t.type,
            }
        )
    return out


def card_for_article(article: Article) -> dict:
    inp = build_article_input(article)
    return {
        "article_id": article.id,
        "word": article.word,
        "translations": inp["translations"],
        "illustrations_ru": inp["illustrations_ru"],
        "tags": article_tags_payload(article),
    }


def baseline_for_article(article: Article) -> dict:
    fields = []
    for asg in article.semantic_assignments.all():
        fields.append(
            {
                "name": asg.field.name,
                "from_translation": asg.from_translation,
            }
        )
    return {
        "article_id": article.id,
        "word": article.word,
        "fields": fields,
        "no_field": len(fields) == 0,
    }


def export_cards_and_baseline(out_dir: Path, article_ids: list[int]) -> None:
    qs = (
        Article.objects.filter(id__in=article_ids)
        .prefetch_related(
            "articleindextranslate_set",
            "additions",
            Prefetch(
                "articleindextag_set",
                queryset=ArticleIndexTag.objects.select_related("tag"),
            ),
            Prefetch(
                "semantic_assignments",
                queryset=ArticleSemanticField.objects.select_related("field"),
            ),
        )
        .order_by("id")
    )
    cards = []
    baseline = []
    by_id = {a.id: a for a in qs}
    missing = [i for i in article_ids if i not in by_id]
    if missing:
        raise SystemExit(f"articles not found: {missing[:20]}…")

    for aid in article_ids:
        art = by_id[aid]
        cards.append(card_for_article(art))
        baseline.append(baseline_for_article(art))

    cards_path = out_path(out_dir, "annotator-cards-pilot.jsonl")
    with cards_path.open("w", encoding="utf-8") as fh:
        for row in cards:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {cards_path} ({len(cards)} cards)")

    # Human-friendly TSV without LLM fields.
    tsv_path = out_path(out_dir, "annotator-cards-pilot.tsv")
    with tsv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(
            [
                "article_id",
                "word",
                "translations",
                "illustrations_ru",
                "tags",
            ]
        )
        for c in cards:
            w.writerow(
                [
                    c["article_id"],
                    c["word"],
                    " | ".join(c["translations"]),
                    " | ".join(c["illustrations_ru"]),
                    " | ".join(f"{t['tag']} ({t['name']})" for t in c["tags"]),
                ]
            )
    print(f"wrote {tsv_path}")

    write_json(out_path(out_dir, "baseline-llm-pilot.json"), {"articles": baseline})


def content_pos_article_ids() -> set[int]:
    return set(
        ArticleIndexTag.objects.filter(tag__tag__in=CONTENT_POS_TAGS).values_list(
            "article_id", flat=True
        )
    )


def articles_with_translation() -> set[int]:
    return set(
        ArticleIndexTranslate.objects.exclude(rus_word__isnull=True)
        .exclude(rus_word="")
        .values_list("article_id", flat=True)
        .distinct()
    )


def build_pilot_sample(out_dir: Path, whitelist_tags: list[str]) -> dict:
    rng = random.Random(PILOT_SEED)
    pos_ids = content_pos_article_ids()
    tr_ids = articles_with_translation()
    pool = sorted(pos_ids & tr_ids)
    if len(pool) < PILOT_RANDOM_N + PILOT_TARGET_N:
        raise SystemExit(f"pool too small: {len(pool)}")

    # Target strata.
    multi_field = set(
        ArticleSemanticField.objects.values("article_id")
        .annotate(n=Count("id"))
        .filter(n__gte=2)
        .values_list("article_id", flat=True)
    )
    no_field = pos_ids & tr_ids - set(
        ArticleSemanticField.objects.values_list("article_id", flat=True)
    )
    subject_tagged = set(
        ArticleIndexTag.objects.filter(tag__tag__in=whitelist_tags).values_list(
            "article_id", flat=True
        )
    )

    # "Thick" ≈ has illustration cyrillic beyond translations — approximate via
    # build_article_input on candidates (sample from multi_field ∪ subject).
    thick_candidates = sorted((multi_field | subject_tagged) & set(pool))
    rng.shuffle(thick_candidates)
    thick: list[int] = []
    for aid in thick_candidates:
        if len(thick) >= 8:
            break
        art = (
            Article.objects.filter(id=aid)
            .prefetch_related("articleindextranslate_set", "additions")
            .first()
        )
        if not art:
            continue
        if build_article_input(art)["illustrations_ru"]:
            thick.append(aid)

    target_buckets = {
        "multi_field": sorted(multi_field & set(pool)),
        "no_field": sorted(no_field & set(pool)),
        "subject_tag": sorted(subject_tagged & set(pool)),
        "thick_illustrations": thick,
    }

    target_ids: list[int] = []
    seen: set[int] = set()

    def take(bucket: str, n: int) -> None:
        nonlocal target_ids
        cand = [i for i in target_buckets[bucket] if i not in seen]
        rng.shuffle(cand)
        for aid in cand[:n]:
            seen.add(aid)
            target_ids.append(aid)

    # 20 targeted: 6 multi, 4 no_field, 5 subject, 5 thick (may overlap strata
    # preferences; fill from remaining multi if short).
    take("multi_field", 6)
    take("no_field", 4)
    take("subject_tag", 5)
    take("thick_illustrations", 5)
    if len(target_ids) < PILOT_TARGET_N:
        take("multi_field", PILOT_TARGET_N - len(target_ids))
    target_ids = target_ids[:PILOT_TARGET_N]

    random_pool = [i for i in pool if i not in seen]
    rng.shuffle(random_pool)
    random_ids = random_pool[:PILOT_RANDOM_N]
    seen.update(random_ids)

    all_ids = sorted(random_ids + target_ids)
    payload = {
        "seed": PILOT_SEED,
        "snapshot_date": "2026-11-02",
        "n_random": len(random_ids),
        "n_target": len(target_ids),
        "filters": {
            "pos_tags": list(CONTENT_POS_TAGS),
            "require_translation": True,
        },
        "random_ids": random_ids,
        "target_ids": target_ids,
        "target_reasons": {
            str(aid): [
                k
                for k, ids in target_buckets.items()
                if aid in ids or aid in set(thick)
            ]
            for aid in target_ids
        },
        "all_ids": all_ids,
    }
    # Fix target_reasons thick membership.
    thick_set = set(thick)
    for aid in target_ids:
        reasons = []
        if aid in multi_field:
            reasons.append("multi_field")
        if aid in no_field:
            reasons.append("no_field")
        if aid in subject_tagged:
            reasons.append("subject_tag")
        if aid in thick_set:
            reasons.append("thick_illustrations")
        payload["target_reasons"][str(aid)] = reasons

    write_json(out_path(out_dir, "sample-pilot-ids.json"), payload)
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        default="data/verification",
        help="Output directory (relative to agents/ or absolute)",
    )
    ap.add_argument(
        "--dump-name",
        default="punzh_dict-20261102-0112.dump",
        help="Source dump filename for snapshot metadata",
    )
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--tags", action="store_true")
    ap.add_argument("--pilot-sample", action="store_true")
    ap.add_argument(
        "--export-cards",
        action="store_true",
        help="Export annotator cards + baseline for pilot ids",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="snapshot + tags + pilot sample + cards",
    )
    args = ap.parse_args()
    if args.all:
        args.snapshot = args.tags = args.pilot_sample = args.export_cards = True
    if not any(
        [args.snapshot, args.tags, args.pilot_sample, args.export_cards]
    ):
        ap.error("pass --all or one of --snapshot/--tags/--pilot-sample/--export-cards")

    out = Path(args.out)
    if not out.is_absolute():
        out = Path(_HERE) / out

    if args.snapshot:
        dump_snapshot(out, args.dump_name)
    if args.tags:
        dump_tag_inventory(out)
    pilot = None
    if args.pilot_sample:
        wl_tags = [x["tag"] for x in DEFAULT_SUBJECT_WHITELIST]
        pilot = build_pilot_sample(out, wl_tags)
    if args.export_cards:
        ids_path = out / "sample-pilot-ids.json"
        if pilot is None:
            if not ids_path.exists():
                raise SystemExit(
                    f"missing {ids_path}; run --pilot-sample first or --all"
                )
            pilot = json.loads(ids_path.read_text(encoding="utf-8"))
        export_cards_and_baseline(out, pilot["all_ids"])


if __name__ == "__main__":
    main()
