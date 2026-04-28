"""Verificador de feeds.

Executa aquest script per saber quins feeds del config.yaml funcionen
des de la teva xarxa, abans de deixar córrer l'agent diari.

Ús:
    python check_feeds.py

Mostra:  ✓ 42  INTEF                https://intef.es/feed/
        ✗  0  Fundació Bofill      https://...     (motiu)

Al final fa un resum dels que has de treure del config.
"""
import sys
from pathlib import Path

import feedparser
import yaml


def main():
    cfg_path = Path("config.yaml")
    if not cfg_path.exists():
        print("❌ No trobo config.yaml. Executa'l des de la carpeta del projecte.")
        sys.exit(1)

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    feeds = cfg.get("sources", {}).get("rss", [])
    if not feeds:
        print("❌ No hi ha feeds configurats a config.yaml")
        sys.exit(1)

    print(f"Verificant {len(feeds)} feeds...\n")

    ok: list[tuple[str, str, int]] = []
    bad: list[tuple[str, str, str]] = []

    for feed in feeds:
        name = feed.get("name", "?")
        url = feed.get("url", "")
        try:
            d = feedparser.parse(url)
            n = len(d.entries)
            if n > 0:
                ok.append((name, url, n))
                print(f"  ✓ {n:>3d}  {name:<40s}")
            else:
                # Pot ser feed buit, mal format, o 403/404
                err_msg = ""
                if d.bozo and d.bozo_exception:
                    err_msg = str(d.bozo_exception)[:60]
                else:
                    err_msg = "0 entrades"
                bad.append((name, url, err_msg))
                print(f"  ✗  --  {name:<40s}  [{err_msg}]")
        except Exception as e:  # noqa: BLE001
            bad.append((name, url, str(e)[:60]))
            print(f"  ✗ ERR  {name:<40s}  [{str(e)[:40]}]")

    print()
    print("─" * 70)
    print(f"RESULTAT: {len(ok)} funcionen · {len(bad)} no funcionen")
    print("─" * 70)

    if bad:
        print("\n⚠  Feeds que NO funcionen (val la pena treure'ls de config.yaml):")
        for name, url, err in bad:
            print(f"   • {name}  ({err})")
            print(f"     {url}")
        print()
        print("Comenta'ls amb '#' al principi de la línia o esborra'ls.")

    if ok:
        total_entries = sum(n for _, _, n in ok)
        print(f"\n✓  Amb els que funcionen, rebràs fins a {total_entries} entrades a revisar per execució.")


if __name__ == "__main__":
    main()
