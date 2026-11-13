"""SQLite contract for the offline mobile dictionary (schema_version = 2).

Stable article/tag ids match the Django/Postgres source. Semantic tables,
rus_lemmas, and FTS are intentionally omitted.
"""

SCHEMA_VERSION = 2
MIN_APP = "0.1.0"
DB_FILENAME = "dict.sqlite"
MANIFEST_FILENAME = "manifest.json"

# DDL applied in order. Keep in sync with docs/plans/mobile-offline.md.
DDL_STATEMENTS = (
    """
    CREATE TABLE meta (
        key TEXT PRIMARY KEY NOT NULL,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE articles (
        id INTEGER PRIMARY KEY NOT NULL,
        word TEXT NOT NULL,
        word_normalized TEXT,
        first_letter TEXT NOT NULL,
        sort_key TEXT NOT NULL,
        article_html TEXT NOT NULL,
        source_id INTEGER,
        source_title TEXT,
        source_detalization TEXT,
        linked_article_id INTEGER
    )
    """,
    """
    CREATE TABLE additions (
        id INTEGER PRIMARY KEY NOT NULL,
        article_id INTEGER NOT NULL,
        article_html TEXT NOT NULL,
        FOREIGN KEY (article_id) REFERENCES articles(id)
    )
    """,
    """
    CREATE TABLE links (
        id INTEGER PRIMARY KEY NOT NULL,
        from_article_id INTEGER NOT NULL,
        to_article_id INTEGER NOT NULL,
        kind TEXT NOT NULL,
        FOREIGN KEY (from_article_id) REFERENCES articles(id),
        FOREIGN KEY (to_article_id) REFERENCES articles(id)
    )
    """,
    """
    CREATE TABLE words (
        id INTEGER PRIMARY KEY NOT NULL,
        article_id INTEGER NOT NULL,
        word TEXT NOT NULL,
        FOREIGN KEY (article_id) REFERENCES articles(id)
    )
    """,
    """
    CREATE TABLE translations (
        id INTEGER PRIMARY KEY NOT NULL,
        article_id INTEGER NOT NULL,
        rus_word TEXT NOT NULL,
        FOREIGN KEY (article_id) REFERENCES articles(id)
    )
    """,
    """
    CREATE TABLE tags (
        id INTEGER PRIMARY KEY NOT NULL,
        tag TEXT NOT NULL,
        name TEXT NOT NULL,
        type INTEGER NOT NULL,
        sorting INTEGER,
        level INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE article_tags (
        article_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        PRIMARY KEY (article_id, tag_id),
        FOREIGN KEY (article_id) REFERENCES articles(id),
        FOREIGN KEY (tag_id) REFERENCES tags(id)
    )
    """,
    "CREATE INDEX idx_articles_letter_sort ON articles(first_letter, sort_key)",
    "CREATE INDEX idx_words_word ON words(word)",
    "CREATE INDEX idx_translations_rus_word ON translations(rus_word)",
    "CREATE INDEX idx_article_tags_tag ON article_tags(tag_id, article_id)",
    "CREATE INDEX idx_additions_article ON additions(article_id)",
    "CREATE INDEX idx_links_from ON links(from_article_id)",
    "CREATE INDEX idx_links_to ON links(to_article_id)",
)

# Tables that must never appear in the mobile package.
FORBIDDEN_TABLE_SUBSTRINGS = (
    "semantic",
    "keyword",
    "rus_lemmas",
    "search_vector",
)
