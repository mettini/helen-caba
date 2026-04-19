"""
Scraper de Airbnb. Parsea la SSR state (niobeClientData) embebida en cada página
de búsqueda. No requiere API key ni headless browser.

Airbnb tiene `<meta robots="noindex">` y pushea anti-bot fuerte — hay que ser
considerado con la cantidad de requests. Por default, 1 request por barrio + 1.5s de espera.

Entrypoint: scrape_all(config) -> list[dict]

Estrategia:
- Búsqueda mensual (monthly_start_date + monthly_length=3) para ver precios de
  estadías largas (3+ meses), que es lo que aplica al caso Helen.
- Por barrio: pedir la página y parsear los ~18 listings que trae.
- Todos los listings Airbnb vienen marcados como `features.amoblado=true`
  (por definición es alquiler temporario amoblado).
- source=`Airbnb`, id=`airbnb-{listingId}`.
"""
from __future__ import annotations
import base64
import json
import re
import time
from datetime import date, timedelta
from urllib import parse as urlparse, request, error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

SCRIPT_RE = re.compile(r'<script id="data-deferred-state-0"[^>]*>([\s\S]+?)</script>')


def _fetch(url: str) -> str:
    req = request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "es-AR,es;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    })
    with request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _listing_id(demand_stay_listing: dict | None) -> str | None:
    """Decodifica el id base64 → 'DemandStayListing:12345' → '12345'."""
    if not demand_stay_listing or "id" not in demand_stay_listing:
        return None
    try:
        raw = base64.b64decode(demand_stay_listing["id"]).decode()
        m = re.match(r"DemandStayListing:(\w+)", raw)
        return m.group(1) if m else None
    except Exception:
        return None


def _parse_price(structured: dict | None) -> tuple[int | None, str | None, int | None, str | None]:
    """Devuelve (precio, moneda, periodo_dias, qualifier_display).
    Airbnb devuelve precios como "$917 USD por 3 meses" o "$321 USD por 5 noches".
    periodo_dias representa a cuántos días cubre ese precio (30=mes, 5=5 noches, etc.).
    """
    if not structured:
        return None, None, None, None
    primary = structured.get("primaryLine") or {}
    raw = (primary.get("discountedPrice") or primary.get("price")
           or (structured.get("secondaryLine") or {}).get("price")
           or "")
    if not raw:
        return None, None, None, None
    m = re.match(r"\$?\s*([\d\.\,]+)\s*(USD|ARS|\$)?", raw.strip())
    if not m:
        return None, None, None, None
    num = re.sub(r"[^\d]", "", m.group(1))
    if not num:
        return None, None, None, None
    cur_raw = m.group(2) or ""
    moneda = "USD" if cur_raw.upper() == "USD" else "ARS"
    precio = int(num)

    qualifier = (primary.get("qualifier") or "").strip()
    q_low = qualifier.lower().replace("\xa0", " ")
    periodo_dias = 30  # default
    if "mensual" in q_low or "mes" in q_low:
        periodo_dias = 30
    elif "noche" in q_low:
        # "por 5 noches" / "por noche"
        mnum = re.search(r"(\d+)", q_low)
        periodo_dias = int(mnum.group(1)) if mnum else 1
    elif "semana" in q_low:
        mnum = re.search(r"(\d+)", q_low)
        periodo_dias = (int(mnum.group(1)) if mnum else 1) * 7
    return precio, moneda, periodo_dias, qualifier or None


def _bedrooms_from_content(sc: dict | None) -> int | None:
    """structuredContent.primaryLine → items con body '1 dormitorio', '1 cama king', etc.
    Si no hay 'dormitorio' pero sí 'cama' → es monoambiente (0 dormitorios).
    (mapPrimaryLine está vacío en vista lista; los datos reales viven en primaryLine.)
    """
    if not sc:
        return None
    items = (sc.get("primaryLine") or []) + (sc.get("mapPrimaryLine") or [])
    for item in items:
        body = (item.get("body") or "").lower()
        m = re.search(r"(\d+)\s*dormitorio", body)
        if m:
            return int(m.group(1))
    has_cama = any("cama" in (item.get("body") or "").lower() for item in items)
    return 0 if has_cama else None


def _extract_features(text: str, keywords: dict) -> dict:
    t = text.lower()
    out = {feat: any(kw in t for kw in kws) for feat, kws in keywords.items()}
    # Airbnb = temporario amoblado por definición
    out["amoblado"] = True
    return out


def _search_url(barrio_display: str, monthly_start: str) -> str:
    """Construye la URL de búsqueda mensual para un barrio dado."""
    q = urlparse.quote(f"{barrio_display}--Capital-Federal--Argentina")
    return (f"https://www.airbnb.com.ar/s/{q}/homes"
            f"?monthly_start_date={monthly_start}&monthly_length=3"
            f"&price_filter_input_type=2"
            f"&room_types%5B%5D=Entire%20home%2Fapt")


def _normalize(r: dict, barrio: str, features_cfg: dict) -> dict | None:
    try:
        dsl = r.get("demandStayListing")
        lid = _listing_id(dsl)
        if not lid:
            return None

        title = (((r.get("nameLocalized") or {}).get("localizedStringWithTranslationPreference"))
                 or r.get("title") or "")
        subtitle = r.get("subtitle") or ""
        precio, moneda, periodo_dias, qualifier = _parse_price(r.get("structuredDisplayPrice"))
        bedrooms = _bedrooms_from_content(r.get("structuredContent"))

        pics = r.get("contextualPictures") or []
        imagenes = [p.get("picture") for p in pics if p.get("picture")]

        # Features sobre título + subtítulo
        blob = f"{title} {subtitle}"
        features = _extract_features(blob, features_cfg)

        # Detectar tipo por título: Airbnb no tiene categoría "PH" — casi todo es Depto o Casa
        tlow = title.lower()
        if " ph " in f" {tlow} " or tlow.startswith("ph "):
            tipo = "PH"
        elif "casa" in tlow:
            tipo = "Casa"
        else:
            tipo = "Depto"

        return {
            "id": f"airbnb-{lid}",
            "source": "Airbnb",
            "inmobiliaria": None,
            "tipo_propiedad": tipo,
            "barrio": barrio,
            "titulo": title,
            "direccion": subtitle or None,
            "precio": precio,
            "moneda": moneda,
            "periodo_dias": periodo_dias,
            "periodo_label": qualifier,  # ej: "por 5 noches", "mensual"
            "expensas": 0,
            "m2": None,
            "ambientes": bedrooms + 1 if bedrooms is not None else None,
            "dormitorios": bedrooms,
            "antiguedad": None,
            "url": f"https://www.airbnb.com.ar/rooms/{lid}",
            "imagenes": imagenes,
            "features": features,
        }
    except Exception as e:
        print(f"    ! normalize failed: {e}")
        return None


def _parse_search_page(html: str) -> list[dict]:
    m = SCRIPT_RE.search(html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        nbd = data.get("niobeClientData") or []
        if not nbd:
            return []
        payload = nbd[0][1]
        return (payload.get("data", {})
                       .get("presentation", {})
                       .get("staysSearch", {})
                       .get("results", {})
                       .get("searchResults", []) or [])
    except Exception as e:
        print(f"    ! airbnb parse error: {e}")
        return []


def scrape_all(config: dict) -> list[dict]:
    src_cfg = config["sources"].get("airbnb", {})
    if not src_cfg.get("habilitado"):
        return []

    sleep = max(config.get("sleep_between_requests", 0.5), 1.5)  # Airbnb: ser considerado
    features_cfg = config["feature_keywords"]

    # Fecha de inicio = primer día del mes próximo (una convención estable)
    today = date.today()
    start = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    monthly_start = start.isoformat()

    all_listings: list[dict] = []
    seen_ids: set = set()

    for b in config["barrios"]:
        barrio = b["nombre"]
        url = _search_url(barrio, monthly_start)
        try:
            html = _fetch(url)
        except error.HTTPError as e:
            print(f"    ! Airbnb {barrio}: HTTP {e.code}")
            continue
        except Exception as e:
            print(f"    ! Airbnb {barrio}: {type(e).__name__}: {e}")
            continue
        raw_results = _parse_search_page(html)
        count_in = 0
        for r in raw_results:
            norm = _normalize(r, barrio, features_cfg)
            if not norm or norm["id"] in seen_ids:
                continue
            seen_ids.add(norm["id"])
            all_listings.append(norm)
            count_in += 1
        print(f"  Airbnb {barrio:18} → {count_in} listings (de {len(raw_results)} totales en la página)")
        time.sleep(sleep)

    return all_listings
