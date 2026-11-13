"""Build an offline mobile package (dict.sqlite + manifest.json) from Postgres."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dict.helpers import krl_sort_key
from dict.models import (
    Article,
    ArticleAddition,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleIndexWord,
    ArticleLink,
    Source,
    Tag,
)

from .schema import (
    DB_FILENAME,
    DDL_STATEMENTS,
    MANIFEST_FILENAME,
    MIN_APP,
    SCHEMA_VERSION,
)

BATCH = 2000


@dataclass(frozen=True)
class MobilePackage:
    """Paths and metadata for a written package."""

    out_dir: Path
    db_path: Path
    manifest_path: Path
    manifest: dict[str, Any]


def export_mobile_package(out_dir: str | Path) -> MobilePackage:
    """Export the current Django DB into out_dir/{dict.sqlite,manifest.json}."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / DB_FILENAME
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        for stmt in DDL_STATEMENTS:
            conn.execute(stmt)
        _write_rows(conn)
        built_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        # data_version is derived from a content hash before it is written into
        # meta (otherwise the hash would include itself).
        _write_meta(conn, built_at=built_at, data_version=None)
        conn.commit()
    finally:
        conn.close()

    content_digest, _ = _sha256_and_size(db_path)
    data_version = content_digest[:12]
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            ("data_version", data_version),
        )
        conn.commit()
    finally:
        conn.close()

    digest, size = _sha256_and_size(db_path)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "data_version": data_version,
        "built_at": built_at,
        "sha256": digest,
        "size": size,
        "min_app": MIN_APP,
        "file": DB_FILENAME,
        # Relative to the pack base URL (…/mobile-pack/).
        "url": DB_FILENAME,
    }
    manifest_path = out / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return MobilePackage(
        out_dir=out,
        db_path=db_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )


def _write_meta(
    conn: sqlite3.Connection,
    *,
    built_at: str,
    data_version: str | None,
) -> None:
    rows: list[tuple[str, str]] = [
        ("schema_version", str(SCHEMA_VERSION)),
        ("built_at", built_at),
        ("min_app", MIN_APP),
    ]
    if data_version is not None:
        rows.append(("data_version", data_version))
    conn.executemany("INSERT INTO meta(key, value) VALUES (?, ?)", rows)


def _write_rows(conn: sqlite3.Connection) -> None:
    sources = {s.id: s.title for s in Source.objects.all().only("id", "title")}

    article_rows = []
    for a in Article.objects.all().iterator(chunk_size=BATCH):
        article_rows.append(
            (
                a.id,
                a.word,
                a.word_normalized,
                a.first_letter,
                krl_sort_key(a.word),
                a.article_html or "",
                a.source_id,
                sources.get(a.source_id) if a.source_id else None,
                a.source_detalization,
                a.linked_article_id,
            )
        )
        if len(article_rows) >= BATCH:
            _insert_articles(conn, article_rows)
            article_rows.clear()
    if article_rows:
        _insert_articles(conn, article_rows)

    _bulk_copy(
        conn,
        """
        INSERT INTO additions(id, article_id, article_html)
        VALUES (?, ?, ?)
        """,
        (
            (row.id, row.article_id, row.article_html or "")
            for row in ArticleAddition.objects.all().iterator(chunk_size=BATCH)
        ),
    )
    _bulk_copy(
        conn,
        """
        INSERT INTO links(id, from_article_id, to_article_id, kind)
        VALUES (?, ?, ?, ?)
        """,
        (
            (row.id, row.from_article_id, row.to_article_id, row.kind)
            for row in ArticleLink.objects.all().iterator(chunk_size=BATCH)
        ),
    )
    _bulk_copy(
        conn,
        """
        INSERT INTO words(id, article_id, word)
        VALUES (?, ?, ?)
        """,
        (
            (row.id, row.article_id, row.word)
            for row in ArticleIndexWord.objects.exclude(word__isnull=True)
            .exclude(word="")
            .iterator(chunk_size=BATCH)
        ),
    )
    _bulk_copy(
        conn,
        """
        INSERT INTO translations(id, article_id, rus_word)
        VALUES (?, ?, ?)
        """,
        (
            (row.id, row.article_id, row.rus_word)
            for row in ArticleIndexTranslate.objects.exclude(rus_word__isnull=True)
            .exclude(rus_word="")
            .only("id", "article_id", "rus_word")
            .iterator(chunk_size=BATCH)
        ),
    )
    _bulk_copy(
        conn,
        """
        INSERT INTO tags(id, tag, name, type, sorting, level)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            (t.id, t.tag, t.name, t.type, t.sorting, t.level)
            for t in Tag.objects.all().iterator(chunk_size=BATCH)
        ),
    )
    _bulk_copy(
        conn,
        """
        INSERT INTO article_tags(article_id, tag_id)
        VALUES (?, ?)
        """,
        (
            (row.article_id, row.tag_id)
            for row in ArticleIndexTag.objects.all().iterator(chunk_size=BATCH)
        ),
    )


def _insert_articles(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.executemany(
        """
        INSERT INTO articles(
            id, word, word_normalized, first_letter, sort_key, article_html,
            source_id, source_title, source_detalization, linked_article_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _bulk_copy(conn: sqlite3.Connection, sql: str, rows) -> None:
    batch: list[tuple] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= BATCH:
            conn.executemany(sql, batch)
            batch.clear()
    if batch:
        conn.executemany(sql, batch)


def _sha256_and_size(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            h.update(chunk)
    return h.hexdigest(), size
