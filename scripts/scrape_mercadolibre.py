"""
Scraper de MercadoLibre Inmuebles. HTML + regex, stdlib only.

La API oficial de ML devuelve 403 desde scraper — pero la UI web es
perfectamente scrapeable. URL pattern:
    https://inmuebles.mercadolibre.com.ar/{tipo}/{operacion}/{provincia}/{barrios}/_Desde_{offset}

Donde `barrios` es `slug1-o-slug2-o-slug3` (hasta N barrios en una misma query).

Dos pasadas:
  1. ph + alquiler + brief barrios — rent tradicional (mayor volumen)
  2. ph + alquiler-temporario + brief barrios — amoblado pre-residencia

Entrypoint: scrape_all(config) -> list[dict]
"""
from __future__ import annotations
import html as html_mod
import re
import time
from urllib import request, error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

BASE = "https://inmuebles.mercadolibre.com.ar/ph/{operacion}/capital-federal/{barrios}/"

ITEM_START = re.compile(r'<li class="ui-search-layout__item[^"]*"')
URL_RE = re.compile(r'href="(https://inmueble\.mercadolibre\.com\.ar/MLA-(\d+)[^"]+)"')
CURRENCY_RE = re.compile(r'andes-money-amount__currency-symbol[^>]*>([^<]+)')
PRICE_RE = re.compile(r'andes-money-amount__fraction[^>]*>([\d\.\,]+)')
TITLE_RE = re.compile(r'class="poly-component__title[^"]*"[^>]*>([\s\S]{0,300}?)</(?:a|h\d|div|span)')
LOCATION_RE = re.compile(r'class="poly-component__location[^"]*"[^>]*>([^<]+)')
ATTR_RE = re.compile(r'<li class="poly-attributes_list__item[^"]*">([^<]+)')
IMG_RE = re.compile(r'<img[^>]+src="(https?://http2\.mlstatic\.com/[^"]+)"')


def _fetch(url: str) -> str:
    req = request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-AR,es;q=0.9"})
    with request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = re.sub(r"<[^>]+>", "", s)
    s = html_mod.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _extract_features(text: str, keywords: dict) -> dict:
    t = text.lower()
    return {feat: any(kw in t for kw in kws) for feat, kws in keywords.items()}


def _parse_attrs(attrs: list[str]) -> tuple[int | None, int | None, int | None, int | None]:
    """['4 ambs.', '2 baños', '146 m² cubiertos', '3 dormitorios'] → (amb, banos, m2, dorm)."""
    amb = banos = m2 = dorm = None
    for a in attrs:
        a_low = a.lower().strip()
        num_m = re.search(r"(\d+)", a_low)
        if not num_m:
            continue
        num = int(num_m.group(1))
        if "amb" in a_low:
            amb = num
        elif "baño" in a_low or "bano" in a_low:
            banos = num
        elif "m²" in a_low or " m2" in a_low or "m2 " in a_low:
            m2 = num
        elif "dormitorio" in a_low:
            dorm = num
    return amb, banos, m2, dorm


def _barrio_match(location: str | None, barrios_cfg: list[dict]) -> str | None:
    """'Gorriti Al 5800, Palermo, Capital Federal' → 'Palermo' (canonical)."""
    if not location:
        return None
    import unicodedata
    def norm(s):
        return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn").strip()
    parts = [p.strip() for p in location.split(",")]
    # Usually "Address, Barrio, Capital Federal"
    # Match any segment against canonical barrios
    for part in parts:
        n = norm(part)
        for b in barrios_cfg:
            if norm(b["nombre"]) == n:
                return b["nombre"]
    return None


def _parse_card(chunk: str, source_barrios: list[dict], features_cfg: dict,
                operacion: str, force_amoblado: bool) -> dict | None:
    url_m = URL_RE.search(chunk)
    if not url_m:
        return None
    url = url_m.group(1).split("#")[0]
    mla_id = url_m.group(2)

    cur_m = CURRENCY_RE.search(chunk)
    pr_m = PRICE_RE.search(chunk)
    precio = None
    moneda = None
    if pr_m:
        raw_num = re.sub(r"[^\d]", "", pr_m.group(1))
        if raw_num:
            precio = int(raw_num)
    if cur_m:
        cur = cur_m.group(1).strip()
        moneda = "USD" if "US" in cur else "ARS"

    title_m = TITLE_RE.search(chunk)
    titulo = _clean(title_m.group(1)) if title_m else ""
    loc_m = LOCATION_RE.search(chunk)
    location = _clean(loc_m.group(1)) if loc_m else None
    attrs = [a.strip() for a in ATTR_RE.findall(chunk)]
    amb, banos, m2, dorm = _parse_attrs(attrs)

    # Dirección: primer segmento de location
    direccion = location.split(",")[0].strip() if location else None
    barrio = _barrio_match(location, source_barrios)
    if not barrio:
        return None  # fuera de los barrios del brief

    imgs = []
    seen = set()
    for im in IMG_RE.finditer(chunk):
        u = im.group(1)
        if u not in seen:
            seen.add(u)
            imgs.append(u)

    blob = f"{titulo} {location or ''} {' '.join(attrs)}"
    features = _extract_features(blob, features_cfg)
    if force_amoblado:
        features["amoblado"] = True

    periodo_dias = 30
    periodo_label = "mensual"
    if operacion == "alquiler-temporario":
        # MercadoLibre muestra precio mensual para alquiler-temporario también
        periodo_label = "mensual (temporario)"

    return {
        "id": f"ml-{mla_id}",
        "source": "MercadoLibre",
        "inmobiliaria": None,  # ML no expone inmobiliaria en la card
        "tipo_propiedad": "PH",  # URL filtra por PH
        "barrio": barrio,
        "titulo": titulo or "",
        "direccion": direccion,
        "precio": precio,
        "moneda": moneda,
        "periodo_dias": periodo_dias,
        "periodo_label": periodo_label,
        "expensas": None,
        "m2": m2,
        "ambientes": amb,
        "dormitorios": dorm,
        "antiguedad": None,
        "url": url,
        "imagenes": imgs,
        "features": features,
    }


def _scrape_operacion(operacion: str, barrios_slugs: list[str], source_barrios: list[dict],
                       features_cfg: dict, sleep: float, max_pages: int,
                       force_amoblado: bool, label: str) -> list[dict]:
    barrios_url = "-o-".join(barrios_slugs)
    base = BASE.format(operacion=operacion, barrios=barrios_url)
    all_listings: list[dict] = []
    seen_ids: set = set()
    offset = 0
    page = 1
    while page <= max_pages:
        url = base + (f"_Desde_{offset+1}" if offset > 0 else "")
        try:
            html = _fetch(url)
        except error.HTTPError as e:
            print(f"    ! ML [{label}] p{page}: HTTP {e.code}")
            break
        except Exception as e:
            print(f"    ! ML [{label}] p{page}: {type(e).__name__}: {e}")
            break
        starts = [m.start() for m in ITEM_START.finditer(html)]
        if not starts:
            break
        new_this_page = 0
        for i, start in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(html)
            chunk = html[start:end]
            listing = _parse_card(chunk, source_barrios, features_cfg, operacion, force_amoblado)
            if not listing or listing["id"] in seen_ids:
                continue
            seen_ids.add(listing["id"])
            all_listings.append(listing)
            new_this_page += 1
        print(f"  ML [{label}] p{page} offset={offset}: {new_this_page} nuevos (de {len(starts)} items)")
        if new_this_page == 0:
            break
        offset += 48
        page += 1
        time.sleep(sleep)
    return all_listings


def scrape_all(config: dict) -> list[dict]:
    src_cfg = config["sources"].get("mercadolibre", {})
    if not src_cfg.get("habilitado"):
        return []

    sleep = config.get("sleep_between_requests", 0.5)
    max_pages = src_cfg.get("max_pages", 6)
    features_cfg = config["feature_keywords"]
    barrios_cfg = config["barrios"]
    # slugs para la URL (basados en nombre canónico)
    barrios_slugs = [b["slug"] for b in barrios_cfg]

    # Pass 1: alquiler tradicional
    p1 = _scrape_operacion("alquiler", barrios_slugs, barrios_cfg, features_cfg,
                            sleep, max_pages, force_amoblado=False, label="PH alquiler")
    # Pass 2: alquiler temporario (amoblado por default)
    p2 = _scrape_operacion("alquiler-temporario", barrios_slugs, barrios_cfg, features_cfg,
                            sleep, max_pages, force_amoblado=True, label="PH temporario (amoblado)")

    by_id: dict[str, dict] = {l["id"]: l for l in p1}
    for l in p2:
        if l["id"] not in by_id:
            by_id[l["id"]] = l
    return list(by_id.values())
