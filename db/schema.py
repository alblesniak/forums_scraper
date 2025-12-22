from __future__ import annotations

import sqlite3


def ensure_lpmn_tokens_table(connection: sqlite3.Connection) -> None:
    """Ensure the table for LPMN token output exists."""
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS post_lpmn_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            token_order INTEGER NOT NULL,
            sentence_order INTEGER,
            orth TEXT NOT NULL,
            lemma TEXT,
            ctag TEXT,
            lexemes_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_post_lpmn_tokens_post
        ON post_lpmn_tokens(post_id)
        """
    )
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_post_lpmn_tokens_unique
        ON post_lpmn_tokens(post_id, token_order)
        """
    )
    connection.commit()
