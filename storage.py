"""Deduplicació persistent amb SQLite.

El fitxer `events.db` és commitejat al repo per GitHub Actions després de cada
execució, de manera que l'estat persisteix entre dies sense infraestructura
externa.
"""
import sqlite3


class EventStore:
    def __init__(self, path: str):
        self.path = path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_events (
                    hash    TEXT PRIMARY KEY,
                    titol   TEXT,
                    url     TEXT,
                    font    TEXT,
                    seen_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def has_seen(self, event: dict) -> bool:
        with sqlite3.connect(self.path) as c:
            row = c.execute(
                "SELECT 1 FROM seen_events WHERE hash = ?", (event["hash"],)
            ).fetchone()
            return row is not None

    def mark_seen(self, event: dict):
        with sqlite3.connect(self.path) as c:
            c.execute(
                "INSERT OR IGNORE INTO seen_events (hash, titol, url, font) VALUES (?, ?, ?, ?)",
                (
                    event["hash"],
                    event.get("titol", ""),
                    event.get("url", ""),
                    event.get("font", ""),
                ),
            )

    def prune_older_than_days(self, days: int = 180):
        """Elimina registres antics per mantenir la BD petita."""
        with sqlite3.connect(self.path) as c:
            c.execute(
                "DELETE FROM seen_events WHERE seen_at < datetime('now', ?)",
                (f"-{days} days",),
            )
