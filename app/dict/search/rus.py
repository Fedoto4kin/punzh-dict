"""Russian translation search pipeline (ILIKE, tokens, ?f=, related)."""

import re
from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Q

from dict.helpers import (
    FUZZY_TOKEN_MIN_LEN,
    STOP_1A,
    STOP_1B,
    STOPWORDS,
    TOKEN_RE,
    query_tokens,
    token_boundary_fuzzy_regex,
    token_boundary_regex,
)
from dict.models import Article, ArticleIndexTranslate, ArticleLink

from .common import Content, expand_by_links, get_sorted_articles


# Token/stopword primitives: dict.helpers.rus_tokens (shared with AI / audits).
# Compat aliases for callers that still import private names from search.
_TOKEN_RE = TOKEN_RE
_STOP_1A = STOP_1A
_STOP_1B = STOP_1B
_query_tokens = query_tokens
_token_boundary_regex = token_boundary_regex
_token_boundary_fuzzy_regex = token_boundary_fuzzy_regex
_FUZZY_TOKEN_MIN_LEN = FUZZY_TOKEN_MIN_LEN

# Anchor queries where token-OR hits are huge: narrowing candidates only from
# ILIKE-exact articles (backlog §2 prio-filter «быть»).
HIGH_FREQ_ANCHOR_QUERIES = frozenset({"быть"})


def _translate_q_any_query_token(tokens):
    """OR: rus_word contains at least one query token as a whole word."""
    combined = Q()
    for tok in tokens:
        combined |= Q(rus_word__iregex=token_boundary_regex(tok))
        if len(tok) >= FUZZY_TOKEN_MIN_LEN:
            combined |= Q(rus_word__iregex=token_boundary_fuzzy_regex(tok))
    return combined


def _strip_parens_for_key(phrase):
    """Parenthetical glosses (о корове), (детс.) — excluded from key unless head is only the query."""
    return re.sub(r"\([^)]*\)", " ", phrase)


def _paren_gloss_tokens(phrase):
    """Lowercase tokens taken from (…) segments."""
    gloss = " ".join(re.findall(r"\(([^)]*)\)", phrase))
    if not gloss:
        return []
    return _TOKEN_RE.findall(gloss.lower())


def _label_and_key_tokens(phrase, query_words, stopwords):
    key_source = _strip_parens_for_key(phrase)
    toks = _TOKEN_RE.findall(key_source.lower())
    label_toks = [t for t in toks if t not in query_words]
    key_toks = [t for t in label_toks if t not in stopwords]
    if not key_toks:
        # «случаться (о домашних животных)»: distinguisher lives only in parens.
        paren_toks = _paren_gloss_tokens(phrase)
        key_toks = [
            t for t in paren_toks if t not in query_words and t not in stopwords
        ]
    return label_toks, key_toks


def _blob_matches_key_tokens(blob, key_tokens):
    """All key tokens must appear in the blob (substring, same as ?f= filter)."""
    if not key_tokens:
        return False
    return all(tok in blob for tok in key_tokens)


def split_by_coverage(candidates, page_blobs, query_words, stopwords):
    """
    Classify suggestion phrases into narrowing tags relative to the anchor's
    result set. No "similar" class (SPEC v2 §0, §2): candidates come from the
    anchor's own full-text hits, so every key is inside the result set.

    candidates : suggestion phrases (rus_word), e.g. "быстро ехать".
    page_blobs : per-card joined lowercase translations of the result set.
    query_words: set of the query's own tokens, dropped from KEY by EXACT match.
    stopwords  : tokens dropped from the KEY only (kept in the label).

    LABEL = full candidate phrase (shown on the button).
    KEY   = phrase minus parens, query words, stopwords -> matched by ?f= (AND).
      If that yields an empty key, tokens from (…) are used instead
      («случаться (о домашних животных)» -> key «домашних животных»).
    COVERAGE = cards whose blob contains every key token as a substring.
      0 < coverage < N -> narrowing;  coverage in {0, N} or empty key -> dropped.

    Returns narrowing: [{"label","key","coverage"}], deduped by key
    (first label wins), sorted by descending coverage (broader tags first),
    then by label for ties.
    """
    blobs = [b.lower() for b in page_blobs]
    N = len(blobs)

    seen_keys = set()
    narrowing = []

    for phrase in candidates:
        label_toks, key_toks = _label_and_key_tokens(phrase, query_words, stopwords)
        if not key_toks:
            continue
        key = " ".join(key_toks)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        coverage = sum(1 for b in blobs if _blob_matches_key_tokens(b, key_toks))
        if coverage == 0 or coverage == N:
            continue

        narrowing.append({"label": phrase, "key": key, "coverage": coverage})

    narrowing.sort(key=lambda e: (-e["coverage"], e["label"]))

    return narrowing


def find_exact_match_ids(result_ids, ilike_ids, blobs_by_article, links):
    """
    Exact matches for ?f=exact (query-normalized ILIKE on rus_word):
      * article has at least one rus_word equal to the query (ilike_ids);
      * inherited: no translations of its own, linked (either direction,
        one hop within result_ids) to such an ILIKE hit (rutoldi -> «см. ruttoh»).

    Link-expanded articles that have their own translations but no exact
    rus_word match are excluded (e.g. ehatta with only «быстро ехать»).
    """
    ilike_in_result = set(ilike_ids) & set(result_ids)
    translationless = set(result_ids) - set(blobs_by_article.keys())
    inherited = {
        aid for aid in translationless if links.get(aid, set()) & ilike_in_result
    }
    return ilike_in_result | inherited


def find_related_queries(ilike_ids, blobs_by_article, query_words):
    """
    One-word rus_word synonyms from articles with a direct ILIKE hit on the query.
    Other single-token translations of the same card, minus query tokens; deduped.
    """
    seen = set()
    related = []
    for aid in ilike_ids:
        for rw in blobs_by_article.get(aid, []):
            if not rw:
                continue
            toks = _TOKEN_RE.findall(rw.lower())
            if len(toks) != 1:
                continue
            tok = toks[0]
            if tok in query_words or tok in seen:
                continue
            seen.add(tok)
            related.append(tok)
    related.sort()
    return related


@dataclass
class RusSearchCore:
    """Intermediate sets for the Russian search pipeline (public + debug)."""

    query: str
    query_tokens: list
    ids_ilike: set
    token_match_ids: set
    seed_ids: set
    expanded_ids: set
    result_ids: set
    blobs_by_article: dict
    links: dict
    narrowing: list
    direct_ids: set
    related_queries: list
    filtered_ids: set
    f: object
    high_freq_anchor: bool
    candidates: list


def rus_search_core(query: str, f=None, expand_links=True) -> RusSearchCore:
    """
    Full Russian lexical pipeline without pagination.
    `query` must already be ё→е normalized (as in views.search).
    expand_links=False — seed hits only (no см./от cluster); used by AI rank.
    """
    # 1. ILIKE (exact rus_word match, case-insensitive)
    ids_ilike = set(
        ArticleIndexTranslate.objects.filter(rus_word__ilike=query).values_list(
            "article_id", flat=True
        )
    )

    # 2. Token match (OR): any query token as a whole word in rus_word (no stemmer).
    query_tokens = _query_tokens(query)
    token_q = _translate_q_any_query_token(query_tokens) if query_tokens else Q(pk=-1)

    token_match_ids = (
        set(
            ArticleIndexTranslate.objects.filter(token_q).values_list(
                "article_id", flat=True
            )
        )
        - ids_ilike
    )

    # 3. Объединяем
    seed_ids = ids_ilike | token_match_ids
    all_ids = list(seed_ids)

    # 4. Расширяем через связи ArticleLink (optional)
    expanded_ids = expand_by_links(all_ids) if expand_links else set(all_ids)

    # 5. Кандидаты для сужающих тегов (SPEC v2, механизм 1)
    high_freq_anchor = query.strip().lower() in HIGH_FREQ_ANCHOR_QUERIES
    candidate_article_ids = ids_ilike if high_freq_anchor else expanded_ids
    candidates = list(
        ArticleIndexTranslate.objects.filter(
            token_q, article_id__in=candidate_article_ids
        )
        .values_list("rus_word", flat=True)
        .distinct()
    )

    # Множество, реально попавшее в выдачу
    result_ids = expanded_ids if expanded_ids else ids_ilike

    # page_blobs: переводы по каждой карточке выдачи, ОДНИМ запросом
    blobs_by_article = {}
    for aid, rus_word in ArticleIndexTranslate.objects.filter(
        article_id__in=result_ids
    ).values_list("article_id", "rus_word"):
        if rus_word:
            blobs_by_article.setdefault(aid, []).append(rus_word)
    page_blobs = [" | ".join(v) for v in blobs_by_article.values()]

    query_words = set(_TOKEN_RE.findall(query.lower()))
    narrowing = split_by_coverage(candidates, page_blobs, query_words, STOPWORDS)

    # Связи внутри выдачи (обе стороны) — для наследования точных попаданий
    links = {}
    for fa, ta in ArticleLink.objects.filter(
        from_article_id__in=result_ids,
        to_article_id__in=result_ids,
        kind__in=ArticleLink.KINDS_LISTING,
    ).values_list("from_article_id", "to_article_id"):
        links.setdefault(fa, set()).add(ta)
        links.setdefault(ta, set()).add(fa)
    direct_ids = find_exact_match_ids(result_ids, ids_ilike, blobs_by_article, links)
    related_queries = find_related_queries(ids_ilike, blobs_by_article, query_words)

    # Фильтр применяется ПОСЛЕ вычисления тегов/прямых (они всегда от полного
    # якоря) и ДО пагинации, чтобы номера страниц и n-граммы совпадали с
    # отфильтрованным набором.
    # f=None / f=all → полная выдача; f=exact → точные; иначе ключ тега.
    filtered_ids = result_ids
    if f == "exact":
        filtered_ids = set(result_ids) & direct_ids
    elif f and f != "all":
        # f — ключ тега: все токены ключа должны быть в блобе переводов (AND).
        f_tokens = _TOKEN_RE.findall(f.lower())
        kept = set()
        for aid, rus_words in blobs_by_article.items():
            blob = " | ".join(rus_words).lower()
            if _blob_matches_key_tokens(blob, f_tokens):
                kept.add(aid)
        filtered_ids = set(result_ids) & kept

    return RusSearchCore(
        query=query,
        query_tokens=query_tokens,
        ids_ilike=ids_ilike,
        token_match_ids=token_match_ids,
        seed_ids=seed_ids,
        expanded_ids=expanded_ids,
        result_ids=result_ids,
        blobs_by_article=blobs_by_article,
        links=links,
        narrowing=narrowing,
        direct_ids=direct_ids,
        related_queries=related_queries,
        filtered_ids=filtered_ids,
        f=f,
        high_freq_anchor=high_freq_anchor,
        candidates=candidates,
    )


def search_by_translate_linked(query: str, page=1, f=None):
    core = rus_search_core(query, f=f)
    page_obj, found_count = get_sorted_articles(core.filtered_ids, page)
    # Exact set covers the whole wide listing — no point offering «all».
    wide_equals_exact = bool(core.direct_ids) and len(core.direct_ids) == len(
        core.result_ids
    )
    return (
        page_obj,
        found_count,
        core.narrowing,
        core.direct_ids,
        core.related_queries,
        wide_equals_exact,
    )
