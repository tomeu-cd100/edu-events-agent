"""Agent diari de cerca d'esdeveniments educatius (versió sense IA).

Pipeline:
  1. Recol·lecta esdeveniments de feeds RSS configurats
  2. Descarta els ja vistos (SQLite)
  3. Filtra per regles segons puntuació de paraules clau
  4. Envia un correu HTML amb les troballes
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from filter_rules import filter_events
from mailer import send_email
from rss import fetch_rss_feeds
from storage import EventStore

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DB_PATH = "events.db"


def main():
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    today = datetime.now().strftime("%d/%m/%Y")

    log.info("1/4 · Recol·lectant esdeveniments de les fonts RSS...")
    raw_events = fetch_rss_feeds(cfg["sources"]["rss"])
    log.info("  → %d esdeveniments bruts", len(raw_events))

    log.info("2/4 · Deduplicant contra històric...")
    store = EventStore(DB_PATH)
    store.prune_older_than_days(180)
    new_events = [e for e in raw_events if not store.has_seen(e)]
    log.info("  → %d nous", len(new_events))

    if not new_events:
        send_email(
            subject=f"[Agent Edu] {today} · Sense novetats",
            html="<p>L'agent ha revisat les fonts i no ha trobat cap esdeveniment nou avui.</p>",
        )
        return

    log.info("3/4 · Aplicant filtre per regles...")
    relevant = filter_events(new_events, cfg["filter"])

    # Marca TOTS els nous com a vistos (rellevants o no) per no reprocessar-los
    for e in new_events:
        store.mark_seen(e)

    if not relevant:
        send_email(
            subject=f"[Agent Edu] {today} · Sense troballes rellevants",
            html=(
                f"<p>S'han revisat <strong>{len(new_events)}</strong> esdeveniments nous, "
                "cap ha passat el filtre de rellevància.</p>"
                "<p style='color:#999;font-size:12px'>Si penses que hauria d'haver-n'hi, "
                "revisa les paraules clau a <code>config.yaml</code>.</p>"
            ),
        )
        return

    log.info("4/4 · Enviant correu amb les troballes...")
    html = render_html(relevant, total_revisats=len(new_events))
    send_email(
        subject=f"[Agent Edu] {today} · {len(relevant)} troballes",
        html=html,
    )
    log.info("Fet.")


def render_html(events: list[dict], total_revisats: int) -> str:
    # Agrupa per categoria, mantenint l'ordre del config.yaml
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    cat_order = [c["name"] for c in cfg.get("filter", {}).get("categories", [])]

    grouped: dict[str, list[dict]] = {name: [] for name in cat_order}
    for e in events:
        cat = e.get("categoria") or (cat_order[-1] if cat_order else "Troballes")
        grouped.setdefault(cat, []).append(e)

    # Construeix índex i seccions
    nav_links = []
    sections_html = []
    for cat_name in cat_order or list(grouped.keys()):
        items = grouped.get(cat_name, [])
        if not items:
            continue
        anchor = "cat-" + str(abs(hash(cat_name)))[:8]
        nav_links.append(
            f'<a href="#{anchor}" style="color:#0a66c2;text-decoration:none;'
            f'margin-right:16px;font-size:13px">{cat_name} ({len(items)})</a>'
        )
        sections_html.append(_render_section(cat_name, anchor, items))

    nav_html = (
        '<div style="background:#f5f7fa;padding:12px 16px;border-radius:6px;margin-bottom:20px">'
        + "".join(nav_links)
        + "</div>"
    )

    return f"""
    <html>
      <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#222;max-width:780px;margin:0 auto;padding:16px">
        <h2 style="margin:0 0 4px 0">Troballes del {datetime.now():%d/%m/%Y}</h2>
        <p style="color:#666;margin:0 0 16px 0;font-size:13px">
          {len(events)} esdeveniments rellevants · {total_revisats} revisats avui
        </p>
        {nav_html}
        {''.join(sections_html)}
        <p style="color:#999;font-size:11px;margin-top:24px">
          Generat automàticament · edu-events-agent (filtre per regles) ·
          La "data" pot ser la de publicació del feed, no la de l'esdeveniment.
        </p>
      </body>
    </html>
    """


def _render_section(cat_name: str, anchor: str, items: list[dict]) -> str:
    rows = []
    for e in items:
        data_nota = ""
        if e.get("data_origen"):
            data_nota = f"<div style='color:#999;font-size:11px'>({e['data_origen']})</div>"
        rows.append(
            f"""
            <tr style="border-top:1px solid #e5e5e5">
              <td style="padding:12px 8px;vertical-align:top">
                <div style="font-weight:600;font-size:15px">{e.get('nom','(sense títol)')}</div>
                <div style="color:#666;font-size:13px;margin-top:4px">{e.get('resum','')}</div>
                <div style="color:#999;font-size:11px;margin-top:6px;font-style:italic">
                  Font: {e.get('font','?')} · Score: {e.get('score',0)} · {e.get('motius','')}
                </div>
              </td>
              <td style="padding:12px 8px;vertical-align:top;white-space:nowrap;font-size:13px">
                {e.get('data','—')}
                {data_nota}
              </td>
              <td style="padding:12px 8px;vertical-align:top">
                <a href="{e.get('enllac','#')}" style="color:#0a66c2;text-decoration:none;font-size:13px">Obrir →</a>
              </td>
            </tr>
            """
        )
    return f"""
    <h3 id="{anchor}" style="margin:24px 0 8px 0;border-bottom:2px solid #333;padding-bottom:4px">
      {cat_name}
    </h3>
    <table style="border-collapse:collapse;width:100%">
      <thead>
        <tr style="text-align:left;font-size:11px;color:#999;text-transform:uppercase">
          <th style="padding:6px 8px">Esdeveniment</th>
          <th style="padding:6px 8px">Data</th>
          <th style="padding:6px 8px"></th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    """


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        log.exception("Error a l'execució diària")
        try:
            send_email(
                subject="[Agent Edu] ⚠️ Error a l'execució",
                html=f"<pre style='font-family:monospace;color:#c00'>{exc}</pre>",
            )
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)
