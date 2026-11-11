"""
Declarative retrieval profiles for AI search.

Readable config: axes/flags → named id-sets → main ∪ demote.
Interpreter lives in search.search_by_parsed; this module is the rule table.

See docs/plans/ai-search-retrieval-schemas.md and
docs/method-ai-search-retrieval.md.
"""

from __future__ import annotations

from dataclasses import dataclass


# Closed vocabulary of set names resolved in search_by_parsed.
SET_NAMES = frozenset(
    {
        "anchors",
        "tier1",
        "tier2",
        "field_pool",
        "field_tr",
        "field_kw",
        "content",
        "field_and_stylistic",
        "content_and_stylistic",
        "field_kw_and_stylistic",
        "stylistic",
        "pos",
        "soft",
        "dialect",
        "place",
        "geo",
    }
)

# empty_policy values (shared post-step when main is empty).
EMPTY_NONE = "none"
EMPTY_BROWSE_THEME_DIALECT = "browse_theme_dialect"
EMPTY_RELAX_GEO = "relax_geo"
EMPTY_GEO_ALL = "geo_all"
EMPTY_BROWSE_THEN_RELAX = "browse_then_relax"  # theme: browse ∩ geo, else relax


@dataclass(frozen=True)
class ProfileWhen:
    """
    Match flags. None = ignore that axis.

    Flags are derived in search_by_parsed before matching (not free-form code).
    """

    label_theme: bool | None = None
    has_stylistic_hard: bool | None = None
    has_field_and_stylistic: bool | None = None
    has_content: bool | None = None
    has_theme: bool | None = None
    has_geo: bool | None = None


@dataclass(frozen=True)
class MatchContext:
    """Runtime flags for ProfileWhen (built once per query)."""

    label_theme: bool = False
    has_stylistic_hard: bool = False
    has_field_and_stylistic: bool = False
    has_content: bool = False
    has_theme: bool = False
    has_geo: bool = False


@dataclass(frozen=True)
class RetrievalProfile:
    """
    One retrieval rule.

    main / content / fallback_main: union of named sets (no mini-DSL).
    Intersections are pre-resolved as their own set names.
    """

    name: str
    when: ProfileWhen
    main: tuple[str, ...]
    content: tuple[str, ...] = ()
    zero_kw_score: bool = False
    # Articles in main but outside these sets → demote (e.g. tier1 for label_theme).
    demote_except: tuple[str, ...] = ()
    empty_policy: str = EMPTY_NONE
    # If main ∪ is empty: use fallback_main and optionally drop stylistic hard tags.
    fallback_main: tuple[str, ...] = ()
    drop_stylistic_on_fallback: bool = False
    # label_theme: score lex/field_tr from content; prefer primary field name.
    pin_score_to_content: bool = False
    prefer_primary_field: bool = False
    notes: str = ""


def _when_matches(when: ProfileWhen, ctx: MatchContext) -> bool:
    pairs = (
        (when.label_theme, ctx.label_theme),
        (when.has_stylistic_hard, ctx.has_stylistic_hard),
        (when.has_field_and_stylistic, ctx.has_field_and_stylistic),
        (when.has_content, ctx.has_content),
        (when.has_theme, ctx.has_theme),
        (when.has_geo, ctx.has_geo),
    )
    for expected, actual in pairs:
        if expected is not None and expected != actual:
            return False
    return True


def match_profile(
    ctx: MatchContext, profiles: tuple[RetrievalProfile, ...] | None = None
):
    """First matching profile in order wins."""
    for profile in profiles or PROFILES:
        if _when_matches(profile.when, ctx):
            return profile
    return None


def union_named(sets: dict[str, set], names: tuple[str, ...]) -> set:
    out: set = set()
    for name in names:
        out |= sets.get(name) or set()
    return out


def validate_profiles(
    profiles: tuple[RetrievalProfile, ...] | None = None
) -> list[str]:
    """Return list of problems (empty = ok). For tests / import checks."""
    problems = []
    seen = set()
    for p in profiles or PROFILES:
        if p.name in seen:
            problems.append(f"duplicate profile name {p.name!r}")
        seen.add(p.name)
        for attr in ("main", "content", "fallback_main", "demote_except"):
            for name in getattr(p, attr):
                if name not in SET_NAMES:
                    problems.append(f"{p.name}.{attr}: unknown set {name!r}")
        if p.empty_policy not in {
            EMPTY_NONE,
            EMPTY_BROWSE_THEME_DIALECT,
            EMPTY_RELAX_GEO,
            EMPTY_GEO_ALL,
            EMPTY_BROWSE_THEN_RELAX,
        }:
            problems.append(f"{p.name}: bad empty_policy {p.empty_policy!r}")
    return problems


# ---------------------------------------------------------------------------
# Profiles v1 (order = priority). Keep six; do not merge yet.
# ---------------------------------------------------------------------------

PROFILES: tuple[RetrievalProfile, ...] = (
    RetrievalProfile(
        name="label_theme",
        when=ProfileWhen(label_theme=True, has_stylistic_hard=False),
        main=("tier1", "tier2"),
        content=("tier1",),
        zero_kw_score=True,
        demote_except=("tier1",),
        empty_policy=EMPTY_BROWSE_THEN_RELAX,
        pin_score_to_content=True,
        prefer_primary_field=True,
        notes=(
            "Dialect/place + lemma in field label. "
            "tier1=anchors∩geo, tier2=field∩geo; no KW score; demote below tier1."
        ),
    ),
    RetrievalProfile(
        name="field_and_mark",
        when=ProfileWhen(
            has_stylistic_hard=True,
            has_field_and_stylistic=True,
        ),
        main=("field_and_stylistic",),
        empty_policy=EMPTY_BROWSE_THEN_RELAX,
        notes="Stylistic hard ∩ primary field.",
    ),
    RetrievalProfile(
        name="content_and_mark",
        when=ProfileWhen(
            has_stylistic_hard=True,
            has_content=True,
        ),
        main=("content_and_stylistic", "field_kw_and_stylistic"),
        fallback_main=("content", "field_kw"),
        drop_stylistic_on_fallback=True,
        empty_policy=EMPTY_BROWSE_THEN_RELAX,
        notes="Content∩mark; if empty drop mark and keep content∪field_kw.",
    ),
    RetrievalProfile(
        name="mark_browse",
        when=ProfileWhen(has_stylistic_hard=True),
        main=("stylistic",),
        empty_policy=EMPTY_GEO_ALL,
        notes="Hard stylistic only (no content).",
    ),
    RetrievalProfile(
        name="geo_browse",
        when=ProfileWhen(
            has_geo=True,
            has_theme=False,
            has_stylistic_hard=False,
            has_content=False,
        ),
        main=("geo",),
        empty_policy=EMPTY_NONE,
        notes="Dialect/place only, e.g. «весьегонский говор».",
    ),
    RetrievalProfile(
        name="content_default",
        when=ProfileWhen(),  # catch-all
        main=("content", "field_tr", "field_kw"),
        empty_policy=EMPTY_BROWSE_THEN_RELAX,
        notes="Lexical/focus (+ field contour); browse/relax if empty after geo AND.",
    ),
)

# Fail fast on import if the table is inconsistent.
_PROFILE_ERRORS = validate_profiles()
if _PROFILE_ERRORS:
    raise RuntimeError("retrieval_schemas: " + "; ".join(_PROFILE_ERRORS))
