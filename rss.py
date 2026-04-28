"""Recol·lector d'esdeveniments via feeds RSS/Atom."""
import logging
from hashlib import sha256

import feedparser

log = logging.getLogger(__name__)

# Límit per feed per no saturar el LLM amb un sol feed molt actiu
MAX_ENTRIES_PER_FEED = 30


def fetch_rss_feeds(feeds: list[dict]) -> list[dict]:
    """Llegeix tots els feeds configurats. Els errors per feed no aturen la resta."""
    events = []
    for feed in feeds:
        try:
            events.extend(_fetch_one(feed["name"], feed["url"]))
        except Exception as exc:  # noqa: BLE001
            log.warning("Error llegint RSS '%s': %s", feed.get("name", "?"), exc)
    return events


def _fetch_one(name: str, url: str) -> list[dict]:
    d = feedparser.parse(url)
    if d.bozo and not d.entries:
        log.warning("Feed buit o mal format: %s (%s)", name, url)
        return []

    out = []
    for entry in d.entries[:MAX_ENTRIES_PER_FEED]:
        titol = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not titol or not link:
            continue
        out.append({
            "font": name,
            "titol": titol,
            "descripcio": entry.get("summary", "") or "",
            "url": link,
            "data_publicacio": entry.get("published", "") or "",
            "hash": _hash(titol + "|" + link),
        })
    log.info("  RSS '%s': %d entrades", name, len(out))
    return out


def _hash(s: str) -> str:
    return sha256(s.strip().lower().encode()).hexdigest()[:16]
