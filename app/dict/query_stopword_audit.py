"""
Corpus scan of Russian translation tokens for query-stopword candidates.

Used by ``audit_query_stopwords``: DF / row counts over ArticleIndexTranslate,
bucket labels against STOPWORDS (1a/1b), suggestions for 1c (len≥3 function
words that flood token-OR in multi-word queries).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

from dict.models import ArticleIndexTranslate
from dict.helpers import STOP_1A, STOP_1B, STOPWORDS, TOKEN_RE

# Leading token inside parenthetical glosses: (о корове), (при ком-л.).
_PAREN_LEAD_RE = re.compile(r"\(([а-яё\-]+)", re.IGNORECASE)

# Linguistic seed for 1c review (not auto-committed). Intersection with high DF
# is what the audit highlights as strong QUERY_STOP candidates.
_FUNCTION_SEED_1C = frozenset(
    {
        "при",
        "для",
        "без",
        "под",
        "над",
        "про",
        "или",
        "как",
        "что",
        "это",
        "все",
        "его",
        "мне",
        "нас",
        "вам",
        "вас",
        "них",
        "ней",
        "ним",
        "чем",
        "чья",
        "чье",
        "чей",
        "кто",
        "где",
        "куда",
        "когда",
        "если",
        "чтобы",
        "через",
        "между",
        "перед",
        "после",
        "около",
        "среди",
        "вместо",
        "кроме",
        "также",
        "только",
        "уже",
        "еще",
        "очень",
        "можно",
        "надо",
        "нужно",
    }
)


@dataclass(frozen=True)
class TokenStat:
    token: str
    length: int
    df: int  # distinct article_id
    rows: int  # rus_word rows containing the token
    paren_lead_df: int  # articles where token leads a (…) gloss
    bucket: str  # stop_1a | stop_1b | missing_1a | candidate_1c | review | content


@dataclass
class QueryStopwordAudit:
    article_count: int
    row_count: int
    distinct_tokens: int
    stats: List[TokenStat]
    suggested_1c: List[str]
    missing_1a: List[str]
    missing_1b_like: List[str]


def _canon_token(tok: str) -> str:
    return tok.lower().replace("ё", "е")


def _bucket(
    token: str,
    df: int,
    *,
    min_df: int,
    max_len_1c: int,
) -> str:
    if token in STOP_1A:
        return "stop_1a"
    if token in STOP_1B:
        return "stop_1b"
    if len(token) <= 2 and df >= min_df:
        return "missing_1a"
    if token.endswith("-л") and token not in STOPWORDS and df >= min_df:
        return "missing_1b"
    # Strong 1c: linguistic seed ∩ high DF. Other short high-DF → review (manual).
    if token in _FUNCTION_SEED_1C and df >= min_df:
        return "candidate_1c"
    if 3 <= len(token) <= max_len_1c and df >= min_df:
        return "review"
    return "content"


def scan_query_stopword_candidates(
    *,
    min_df: int = 30,
    max_len_1c: int = 5,
    top: Optional[int] = None,
    buckets: Optional[Iterable[str]] = None,
) -> QueryStopwordAudit:
    """
    Scan all translation rows. Returns stats sorted by df desc, then token.

    ``buckets`` — if set, keep only those bucket labels in ``stats``
    (suggested lists still use the full scan).
    """
    aids_by_tok: Dict[str, Set[int]] = defaultdict(set)
    rows_by_tok: Dict[str, int] = defaultdict(int)
    paren_aids: Dict[str, Set[int]] = defaultdict(set)
    all_aids: Set[int] = set()
    row_count = 0

    qs = ArticleIndexTranslate.objects.values_list("article_id", "rus_word")
    for article_id, rus_word in qs.iterator(chunk_size=2000):
        if not rus_word:
            continue
        row_count += 1
        all_aids.add(article_id)
        text = rus_word.replace("ё", "е")
        toks = {_canon_token(t) for t in TOKEN_RE.findall(text)}
        for tok in toks:
            aids_by_tok[tok].add(article_id)
            rows_by_tok[tok] += 1
        for m in _PAREN_LEAD_RE.finditer(text):
            paren_aids[_canon_token(m.group(1))].add(article_id)

    stats: List[TokenStat] = []
    for tok, aids in aids_by_tok.items():
        df = len(aids)
        bucket = _bucket(tok, df, min_df=min_df, max_len_1c=max_len_1c)
        stats.append(
            TokenStat(
                token=tok,
                length=len(tok),
                df=df,
                rows=rows_by_tok[tok],
                paren_lead_df=len(paren_aids.get(tok, ())),
                bucket=bucket,
            )
        )

    stats.sort(key=lambda s: (-s.df, s.token))

    suggested_1c = sorted({s.token for s in stats if s.bucket == "candidate_1c"})
    missing_1a = sorted({s.token for s in stats if s.bucket == "missing_1a"})
    missing_1b_like = sorted({s.token for s in stats if s.bucket == "missing_1b"})

    if buckets is not None:
        want = set(buckets)
        stats = [s for s in stats if s.bucket in want]
    if top is not None:
        stats = stats[:top]

    return QueryStopwordAudit(
        article_count=len(all_aids),
        row_count=row_count,
        distinct_tokens=len(aids_by_tok),
        stats=stats,
        suggested_1c=suggested_1c,
        missing_1a=missing_1a,
        missing_1b_like=missing_1b_like,
    )


def format_python_set(name: str, tokens: Iterable[str]) -> str:
    items = sorted(tokens)
    if not items:
        return f"{name} = set()\n"
    lines = [f"{name} = {{"]
    for t in items:
        lines.append(f'    "{t}",')
    lines.append("}")
    return "\n".join(lines) + "\n"


def csv_rows(stats: List[TokenStat]) -> List[dict]:
    return [
        {
            "token": s.token,
            "len": s.length,
            "df": s.df,
            "rows": s.rows,
            "paren_lead_df": s.paren_lead_df,
            "bucket": s.bucket,
            "in_stopwords": "1" if s.token in STOPWORDS else "0",
            "in_seed_1c": "1" if s.token in _FUNCTION_SEED_1C else "0",
        }
        for s in stats
    ]
