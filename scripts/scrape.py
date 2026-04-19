#!/usr/bin/env python3
"""
Orquestador de scraping. Corre todos los sources habilitados en config.json
y escribe site/data.json preservando `hidden` y `notes` de listings previos.

Uso:
    python3 scripts/scrape.py

Sin dependencias externas — solo stdlib. Cada source en su propio módulo:
    scrape_argenprop.py    (HTML + regex, paginado por barrio)
    scrape_remax.py        (API JSON, paginado global con filtro CABA)

Sumar un source nuevo:
    1. Crear scripts/scrape_<nombre>.py con `scrape_all(config) -> list[dict]`.
    2. Agregar entry en config.json bajo "sources".
    3. Importarlo y agregarlo a SOURCES abajo.
"""
from __future__ import annotations
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import scrape_argenprop
import scrape_remax
import scrape_airbnb
import scrape_mercadolibre
import scrape_zonaprop
import scrape_properati


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def property_key(listing: dict) -> str | None:
    """Genera un ID lógico basado en (street + número-buckeado-a-100 + barrio).
    Si no puede parsear la dirección, devuelve None → no dedup, usa el id técnico.

    Ejemplo: "Av. Álvarez Thomas 920, Piso 1" en Colegiales → "alvarez-thomas-900-colegiales".
    Bucketear al centenar más cercano matchea avisos del mismo edificio
    publicados con números ligeramente distintos (ej. 900 y 920).
    """
    addr = listing.get("direccion") or ""
    barrio = listing.get("barrio") or ""
    if not addr or not barrio:
        return None
    addr = re.split(r"(?i),?\s*piso\b", addr)[0]
    addr = _strip_accents(addr).lower()
    addr = re.sub(r"\bav?\.?\b", " ", addr)  # "av." / "avenida"
    addr = re.sub(r"[^a-z0-9\s]", " ", addr)
    addr = re.sub(r"\s+", " ", addr).strip()
    num_m = re.search(r"\d+", addr)
    if not num_m:
        return None
    num = int(num_m.group())
    street = re.sub(r"\d+", "", addr).strip()
    if not street:
        return None
    bucket = (num // 100) * 100
    barrio_n = _strip_accents(barrio).lower().replace(" ", "-")
    street = street.replace(" ", "-")
    return f"{street}-{bucket}-{barrio_n}"

SOURCES = [
    ("argenprop",    scrape_argenprop.scrape_all),
    ("remax",        scrape_remax.scrape_all),
    ("mercadolibre", scrape_mercadolibre.scrape_all),
    ("zonaprop",     scrape_zonaprop.scrape_all),
    ("properati",    scrape_properati.scrape_all),
    ("airbnb",       scrape_airbnb.scrape_all),
]

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "site" / "data.json"
CONFIG_FILE = Path(__file__).resolve().parent / "config.json"


def main() -> int:
    with CONFIG_FILE.open() as f:
        config = json.load(f)

    # Preservar hidden/notes por URL
    preserved: dict[str, dict] = {}
    if DATA_FILE.exists():
        try:
            prior = json.loads(DATA_FILE.read_text())
            for l in prior.get("listings", []):
                keep = {}
                if l.get("hidden"): keep["hidden"] = True
                if l.get("notes"):  keep["notes"] = l["notes"]
                if keep:
                    preserved[l["url"]] = keep
        except Exception as e:
            print(f"  ! no pude leer data.json existente: {e}")

    all_listings: list[dict] = []
    seen_ids: set[str] = set()
    seen_keys: dict[str, dict] = {}  # property_key -> primera listing kept
    dup_by_key = 0
    active_sources: list[str] = []

    for name, fn in SOURCES:
        if not config["sources"].get(name, {}).get("habilitado"):
            continue
        print(f"\n=== {name.upper()} ===")
        for l in fn(config):
            if l["id"] in seen_ids:
                continue
            seen_ids.add(l["id"])
            if l["url"] in preserved:
                l.update(preserved[l["url"]])
            # Dedup por clave lógica (barrio + calle + número-bucket)
            key = property_key(l)
            l["property_key"] = key
            if key and key in seen_keys:
                primary = seen_keys[key]
                primary.setdefault("also_in_sources", []).append({
                    "source": l["source"], "url": l["url"], "inmobiliaria": l.get("inmobiliaria"),
                })
                dup_by_key += 1
                continue
            if key:
                seen_keys[key] = l
            all_listings.append(l)
        active_sources.append(name)

    print(f"\n  (dedup: {dup_by_key} listings suprimidos por aparecer en múltiples fuentes con misma dirección)")

    out = {
        "generatedAt": time.strftime("%Y-%m-%d"),
        "sources": [s.capitalize() for s in active_sources],
        "listings": all_listings,
    }
    DATA_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"\n=== TOTAL: {len(all_listings)} listings → {DATA_FILE.relative_to(ROOT)} ===")

    # Stats finales
    from collections import Counter
    by_source = Counter(l["source"] for l in all_listings)
    for s, n in by_source.most_common():
        print(f"  {s:12} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
