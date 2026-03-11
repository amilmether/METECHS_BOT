import os
import sqlite3
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "history.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS post_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    posted_at           TEXT    NOT NULL,
    youtube_url         TEXT    NOT NULL,
    amazon_url          TEXT,
    product_title       TEXT,
    instagram_media_id  TEXT,
    instagram_permalink TEXT,
    website_product_id  TEXT,
    status              TEXT    NOT NULL DEFAULT 'success'
);
"""


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_TABLE)
    conn.commit()
    return conn


def save_post(
    youtube_url: str,
    amazon_url: str = "",
    product_title: str = "",
    instagram_media_id: str = "",
    instagram_permalink: str = "",
    website_product_id: str = "",
    status: str = "success",
) -> int:
    """Insert a post record and return its row ID.

    Never raises — failures are logged as warnings so the main flow is
    never interrupted by a history write error.
    """
    try:
        with _get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO post_history
                    (posted_at, youtube_url, amazon_url, product_title,
                     instagram_media_id, instagram_permalink, website_product_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    youtube_url,
                    amazon_url,
                    product_title,
                    instagram_media_id,
                    instagram_permalink,
                    website_product_id,
                    status,
                ),
            )
            row_id: int = cur.lastrowid
            log.info(f"[History] Saved post record id={row_id} status={status}")
            return row_id
    except Exception as exc:
        log.warning(f"[History] Could not save post record: {exc}")
        return -1


def get_recent(limit: int = 10) -> list[dict]:
    """Return the most recent *limit* post records as dicts."""
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM post_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log.warning(f"[History] Could not fetch records: {exc}")
        return []
