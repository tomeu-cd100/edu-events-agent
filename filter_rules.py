"""Filtratge per regles (sense IA).

Dona a cada esdeveniment una puntuació segons termes positius/negatius
configurats a `config.yaml`, i genera el format final per al correu.

Limitacions respecte a una solució amb LLM:
- La "durada" no es pot inferir de manera fiable → marquem '—'
- El "resum" és la descripció del feed neta i truncada (no reformulat)
- La "data" prové del feed (published) o d'extracció amb regex del text
"""
import logging
import re
import unicodedata
from datetime import datetime
from html import unescape

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalització de text
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Minúscules + sense accents + sense punt volat, per un matching robust."""
    if not text:
        return ""
    text = text.replace("·", "")  # el NFKD no elimina el punt volat d'intel·ligència
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return text.lower()


def clean_html(html: str) -> str:
    """HTML → text pla simple (suficient per a descripcions de feeds)."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _count_matches(term: str, text_norm: str) -> int:
    """Compta aparicions del terme com a paraula, case-insensitive i sense accents."""
    term_norm = normalize(term)
    if not term_norm:
        return 0
    # \b funciona amb text ascii normalitzat
    pattern = r"\b" + re.escape(term_norm) + r"\b"
    return len(re.findall(pattern, text_norm))


def score_event(event: dict, rules: dict) -> tuple[int, list[str]]:
    """Retorna (puntuació, motius) — els motius són útils per debugar el filtre."""
    title = event.get("titol", "")
    desc = clean_html(event.get("descripcio", ""))

    title_norm = normalize(title)
    body_norm = normalize(title + " " + desc)  # títol compta també al cos
    motius = []

    # 1. Termes negatius: descarten immediatament
    for term in rules.get("negative_terms", []):
        if _count_matches(term, body_norm) > 0:
            return -999, [f"descartat per '{term}'"]

    # 2. Requeriment: ha d'aparèixer almenys un terme de "require_any"
    require_any = rules.get("require_any", [])
    if require_any and not any(_count_matches(t, body_norm) > 0 for t in require_any):
        return 0, ["no conté cap terme de context educatiu"]

    # 3. Termes positius: 1 punt per aparició al cos + bonus si surt al títol
    title_weight = rules.get("title_weight", 2)
    score = 0
    for term in rules.get("positive_terms", []):
        body_hits = _count_matches(term, body_norm)
        title_hits = _count_matches(term, title_norm)
        if body_hits > 0:
            score += body_hits
            score += title_hits * (title_weight - 1)  # extra per ser al títol
            motius.append(f"'{term}' ×{body_hits}" + (" [títol]" if title_hits else ""))

    return score, motius


# ---------------------------------------------------------------------------
# Extracció de dates del text
# ---------------------------------------------------------------------------

MESOS_CA = {
    "gener": 1, "febrer": 2, "marc": 3, "març": 3, "abril": 4, "maig": 5,
    "juny": 6, "juliol": 7, "agost": 8, "setembre": 9, "octubre": 10,
    "novembre": 11, "desembre": 12,
}
MESOS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
MESOS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
ALL_MONTHS = {**MESOS_CA, **MESOS_ES, **MESOS_EN}

# DD/MM/YYYY o DD-MM-YYYY
RE_NUMERIC = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")
# "25 d'abril de 2026" / "25 de abril de 2026"
RE_VERBOSE_CA = re.compile(
    r"\b(\d{1,2})\s+(?:d['e]\s*)?(" + "|".join(ALL_MONTHS.keys()) + r")\s+(?:de\s+)?(\d{4})\b",
    re.IGNORECASE,
)
# "April 25, 2026" / "April 25 2026"
RE_VERBOSE_EN = re.compile(
    r"\b(" + "|".join(ALL_MONTHS.keys()) + r")\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)


def extract_event_date(text: str) -> str | None:
    """Busca una data al text. Prioritza dates futures; si no n'hi ha, la primera trobada."""
    if not text:
        return None
    text_norm = text.replace("·", "")
    text_norm = unicodedata.normalize("NFKD", text_norm).encode("ascii", "ignore").decode()

    candidates: list[datetime] = []

    for m in RE_NUMERIC.finditer(text_norm):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            candidates.append(datetime(y, mo, d))
        except ValueError:
            pass

    for m in RE_VERBOSE_CA.finditer(text_norm):
        d = int(m.group(1))
        mo = ALL_MONTHS.get(m.group(2).lower())
        y = int(m.group(3))
        if mo:
            try:
                candidates.append(datetime(y, mo, d))
            except ValueError:
                pass

    for m in RE_VERBOSE_EN.finditer(text_norm):
        mo = ALL_MONTHS.get(m.group(1).lower())
        d = int(m.group(2))
        y = int(m.group(3))
        if mo:
            try:
                candidates.append(datetime(y, mo, d))
            except ValueError:
                pass

    if not candidates:
        return None

    now = datetime.now()
    future = [c for c in candidates if c >= now]
    chosen = min(future) if future else min(candidates)
    return chosen.strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# Pipeline final
# ---------------------------------------------------------------------------

SUMMARY_MAX_CHARS = 320


def _truncate_smart(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    cut = text[:n]
    # talla a l'últim punt/espai per no partir paraules
    last_stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if last_stop > n * 0.6:
        return cut[: last_stop + 1]
    last_space = cut.rfind(" ")
    if last_space > n * 0.6:
        return cut[:last_space] + "…"
    return cut + "…"


def _categorize(event: dict, categories: list[dict]) -> str:
    """Determina la categoria d'un event segons les regles.

    Retorna el nom de la primera categoria que matxegi. Si cap regla matxeja,
    retorna la categoria marcada amb `default: true`; si tampoc n'hi ha cap,
    retorna "Altres".
    """
    if not categories:
        return "Troballes"

    title = event.get("titol", "")
    desc = clean_html(event.get("descripcio", ""))
    body_norm = normalize(title + " " + desc)

    default_name = "Altres"
    for cat in categories:
        if cat.get("default"):
            default_name = cat.get("name", default_name)
        match_any = cat.get("match_any", [])
        for term in match_any:
            if _count_matches(term, body_norm) > 0:
                return cat.get("name", "Troballes")

    return default_name


def filter_events(events: list[dict], rules: dict) -> list[dict]:
    """Filtra i enriqueix els events. Retorna els que superen `min_score`."""
    min_score = rules.get("min_score", 2)
    categories = rules.get("categories", [])
    out = []

    for e in events:
        score, motius = score_event(e, rules)
        if score < min_score:
            log.debug("Descartat (score=%d) %s — %s", score, e.get("titol", "")[:60], motius)
            continue

        desc_clean = clean_html(e.get("descripcio", ""))
        resum = _truncate_smart(desc_clean, SUMMARY_MAX_CHARS) if desc_clean else "(sense descripció al feed)"

        # Data: primer intenta extreure del text; si no, la del feed
        data_detectada = extract_event_date(e.get("titol", "") + " " + desc_clean)
        if data_detectada:
            data_str = data_detectada
            data_origen = "detectada al text"
        elif e.get("data_publicacio"):
            # Intenta parsejar la data de publicació (format RFC822 habitualment)
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(e["data_publicacio"])
                data_str = dt.strftime("%d/%m/%Y")
                data_origen = "publicació al feed"
            except Exception:  # noqa: BLE001
                data_str = "—"
                data_origen = ""
        else:
            data_str = "—"
            data_origen = ""

        out.append({
            "nom": e.get("titol", "(sense títol)"),
            "font": e.get("font", ""),
            "enllac": e.get("url", ""),
            "data": data_str,
            "data_origen": data_origen,
            "durada_hores": None,  # no es pot determinar sense IA o scraping
            "resum": resum,
            "score": score,
            "motius": ", ".join(motius[:3]),  # 3 principals per l'informe
            "categoria": _categorize(e, categories),
        })

    # Ordena per score descendent: els més rellevants primer
    out.sort(key=lambda x: x["score"], reverse=True)
    log.info("  → %d passen el filtre (min_score=%d)", len(out), min_score)
    return out
