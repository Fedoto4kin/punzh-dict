"""
Public Russian translation register: group ArticleIndexTranslate by rus_word,
browse by letter, filter by word-start prefix (OR across query tokens).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote

from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.functions import Left, Upper

from .classification_survey import article_display_word, article_search_query
from .helpers import (
    MAX_SEARCH_QUERY_LEN,
    prepare_rus_query,
    query_tokens,
    sorted_by_krl,
    token_prefix_regex,
)
from .models import Article, ArticleIndexTranslate

# Ё folded into Е in stored rus_word (canonical_rus_word).
# No Ъ/Ы as initial letters in Russian lemmas (cannot head a register entry).
RUS_ABC = "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЬЭЮЯ"

ROWS_PER_PAGE = 100


@dataclass
class RegisterArticleRef:
    display: str
    search_query: str

    @property
    def search_url(self) -> str:
        return "/search/%s/1" % quote(self.search_query, safe="")


@dataclass
class RegisterRow:
    rus_word: str
    articles: List[RegisterArticleRef]

    @property
    def search_url(self) -> str:
        return "/search/%s/1?f=exact" % quote(self.rus_word, safe="")


@dataclass
class RegisterContent:
    page_obj: object
    letter: Optional[str]
    query: str
    rows: List[RegisterRow]
    letters: str  # RUS_ABC subset that currently has at least one rus_word


def normalize_register_letter(letter: Optional[str]) -> Optional[str]:
    if not letter:
        return None
    ch = letter.upper().replace("Ё", "Е")
    if len(ch) != 1 or ch not in RUS_ABC:
        return None
    return ch


def register_letters_present() -> str:
    """
    Letters from RUS_ABC that actually head at least one rus_word.
    Ordered as in RUS_ABC. Empty register → empty string.
    """
    raw = (
        ArticleIndexTranslate.objects.exclude(rus_word__isnull=True)
        .exclude(rus_word="")
        .annotate(ch=Upper(Left("rus_word", 1)))
        .values_list("ch", flat=True)
        .distinct()
    )
    present = set()
    for ch in raw:
        if not ch:
            continue
        n = ch.replace("Ё", "Е")
        if n in RUS_ABC:
            present.add(n)
    return "".join(c for c in RUS_ABC if c in present)


def register_prefix_filter(raw_query: str) -> Q:
    """
    Word-start prefix OR across tokens. Empty / no tokens → empty Q (no rows).
    Stop-words are kept (unlike lexical token-OR).
    """
    prepared = prepare_rus_query((raw_query or "")[:MAX_SEARCH_QUERY_LEN])
    toks = query_tokens(prepared)
    if not toks:
        return Q(pk__in=[])
    q = Q()
    for tok in toks:
        q |= Q(rus_word__iregex=token_prefix_regex(tok))
    return q


def _matching_rows_qs(letter: Optional[str], query: str):
    qs = ArticleIndexTranslate.objects.exclude(rus_word__isnull=True).exclude(
        rus_word=""
    )
    q = (query or "").strip()
    if q:
        return qs.filter(register_prefix_filter(q))
    letter = normalize_register_letter(letter)
    if not letter:
        return qs.none()
    return qs.filter(rus_word__istartswith=letter)


def build_register_rows(letter: Optional[str], query: str) -> List[RegisterRow]:
    """
    Distinct rus_word groups with Karelian headwords, sorted by rus_word.
    When query is set, letter is ignored (whole-register filter).
    """
    qs = _matching_rows_qs(letter, query)
    pairs = list(qs.values_list("rus_word", "article_id").order_by("rus_word", "id"))
    if not pairs:
        return []

    by_word: dict[str, list[int]] = {}
    for rus_word, article_id in pairs:
        by_word.setdefault(rus_word, [])
        if article_id not in by_word[rus_word]:
            by_word[rus_word].append(article_id)

    article_ids = {aid for aids in by_word.values() for aid in aids}
    articles = {
        a.pk: a for a in Article.objects.filter(pk__in=article_ids).select_related()
    }

    rows: List[RegisterRow] = []
    for rus_word in sorted(by_word.keys(), key=lambda w: w.lower()):
        arts = [articles[aid] for aid in by_word[rus_word] if aid in articles]
        arts.sort(key=lambda a: (sorted_by_krl(a, "word"), a.pk))
        refs = []
        for a in arts:
            display = article_display_word(a)
            search_q = article_search_query(display) or display
            refs.append(RegisterArticleRef(display=display, search_query=search_q))
        rows.append(RegisterRow(rus_word=rus_word, articles=refs))
    return rows


def register_content(
    letter: Optional[str] = None, page: int = 1, query: str = ""
) -> RegisterContent:
    q = (query or "").strip()[:MAX_SEARCH_QUERY_LEN]
    letters = register_letters_present()
    if q:
        letter_out = None
        rows = build_register_rows(None, q)
    else:
        letter_out = normalize_register_letter(letter)
        if letter_out and letter_out in letters:
            rows = build_register_rows(letter_out, "")
        else:
            rows = []

    paginator = Paginator(rows, ROWS_PER_PAGE)
    if page < 1:
        page = 1
    page_obj = paginator.get_page(page)
    return RegisterContent(
        page_obj=page_obj,
        letter=letter_out,
        query=q,
        rows=list(page_obj.object_list),
        letters=letters,
    )
