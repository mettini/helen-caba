"""
Scraper de Properati.

Properati usa curl_cffi (Cloudflare-protected) y NO tiene `/ph` en la URL. Su
estructura es `/s/{barrio}/alquiler?page=N`. Los PHs aparecen mezclados con
deptos y se filtran CLIENT-SIDE buscando la palabra "PH" en el título
(Properati nombra los PHs así: "PH en Alquiler en Colegiales", igual que
"Departamento en Alquiler en Colegiales").

Entrypoint: scrape_all(config) -> list[dict]
"""
from __future__ import annotations
import html as html_mod
import re
import time

try:
    from curl_cffi import requests as cc_requests
except ImportError:
    cc_requests = None


BASE = "https://www.properati.com.ar/s/{barrio}/alquiler"
ARTICLE_RE = re.compile(r'<article[^>]*class[^>]*>')
HREF_RE = re.compile(r'href="(https://www\.properati\.com\.ar/detalle/[^"]+)"')
TITLE_RE = re.compile(r'class="title"[^>]*>([^<]+)')
PRICE_RE = re.compile(r'class="price"[^>]*>([^<]+)')
LOCATION_RE = re.compile(r'class="[^"]*location[^"]*"[^>]*>([^<]+)')
IMG_RE = re.compile(r'(?:src|data-src)="(https?://img\.properati\.com/[^"]+)"')
PUBLISHER_RE = re.compile(r'class="[^"]*publisher[^"]*"[^>]*>([^<]+)')


def _fetch(url: str) -> str:
    if cc_requests is None:
        raise RuntimeError(
            "Properati requiere `curl_cffi`. Instalar: pip3 install --break-system-packages curl_cffi"
        )
    r = cc_requests.get(url, impersonate="chrome120", timeout=30)
    r.raise_for_status()
    return r.text


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


def _parse_price(raw: str | None) -> tuple[int | None, str | None]:
    if not raw:
        return None, None
    raw = raw.strip()
    if raw.lower().startswith("consultar"):
        return None, None
    # "USD 1.500" / "$ 450.000"
    cur = None
    if "usd" in raw.lower() or "us$" in raw.lower():
        cur = "USD"
    elif "$" in raw:
        cur = "ARS"
    num_m = re.search(r"[\d\.\,]+", raw)
    if not num_m:
        return None, cur
    digits = re.sub(r"[^\d]", "", num_m.group(0))
    return (int(digits) if digits else None, cur)


def _parse_attrs_from_text(text: str) -> tuple[int | None, int | None, int | None]:
    """Extrae m², dormitorios, ambientes de la línea de texto del card.
    Texto típico: '1 dormitorio 1,5 baños 44 m²'"""
    dorm_m = re.search(r"(\d+)\s*dormitorio", text, re.IGNORECASE)
    dorm = int(dorm_m.group(1)) if dorm_m else None
    amb_m = re.search(r"(\d+)\s*amb", text, re.IGNORECASE)
    amb = int(amb_m.group(1)) if amb_m else None
    m2_m = re.search(r"(\d+)\s*m²", text)
    m2 = int(m2_m.group(1)) if m2_m else None
    return m2, amb, dorm


def _barrio_match(location: str | None, barrios_cfg: list[dict]) -> str | None:
    if not location:
        return None
    import unicodedata
    def norm(s):
        return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn").strip()
    parts = [p.strip() for p in location.split(",")]
    for part in parts:
        n = norm(part)
        for b in barrios_cfg:
            if norm(b["nombre"]) == n:
                return b["nombre"]
    return None


def _parse_card(chunk: str, barrio_hint: str, barrios_cfg: list[dict], features_cfg: dict) -> dict | None:
    href_m = HREF_RE.search(chunk)
    if not href_m:
        return None
    url = href_m.group(1)
    # UUID from URL
    uuid = url.rsplit("/", 1)[-1]

    title = _clean(TITLE_RE.search(chunk).group(1)) if TITLE_RE.search(chunk) else ""
    title_low = (title or "").lower()
    # Filtro PH: Properati nombra los PHs "PH en Alquiler en {barrio}". Si el título
    # no contiene "ph" como palabra, descartamos (es depto/casa, ya cubiertos por
    # otras fuentes y violarían el brief).
    if not re.search(r"\bph\b", title_low):
        return None

    price_m = PRICE_RE.search(chunk)
    precio, moneda = _parse_price(_clean(price_m.group(1))) if price_m else (None, None)

    loc_m = LOCATION_RE.search(chunk)
    location_str = _clean(loc_m.group(1)) if loc_m else None
    barrio = _barrio_match(location_str, barrios_cfg) or barrio_hint
    if not barrio:
        return None
    direccion = location_str.split(",")[0].strip() if location_str else None

    # Attributes from full text (después de limpiar el card completo)
    text = re.sub(r"<[^>]+>", " ", chunk)
    text = html_mod.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    m2, amb, dorm = _parse_attrs_from_text(text)
    # Si no hay amb pero sí dorm, dorm+1 como proxy (igual que otros scrapers)

    # Publisher — no siempre está con class, cae a None si falta
    pub_m = PUBLISHER_RE.search(chunk)
    inmobiliaria = _clean(pub_m.group(1)) if pub_m else None

    # Images
    imgs = []
    seen = set()
    for im in IMG_RE.finditer(chunk):
        u = im.group(1)
        if u not in seen:
            seen.add(u)
            imgs.append(u)

    features = _extract_features(text, features_cfg)

    return {
        "id": f"pr-{uuid}",
        "source": "Properati",
        "inmobiliaria": inmobiliaria,
        "tipo_propiedad": "PH",
        "barrio": barrio,
        "titulo": title or "",
        "direccion": direccion,
        "precio": precio,
        "moneda": moneda,
        "periodo_dias": 30,
        "periodo_label": "mensual",
        "expensas": None,
        "m2": m2,
        "ambientes": amb,
        "dormitorios": dorm,
        "antiguedad": None,
        "url": url,
        "imagenes": imgs,
        "features": features,
    }


def _scrape_barrio(barrio: dict, barrios_cfg: list[dict], features_cfg: dict,
                    max_pages: int, sleep: float) -> list[dict]:
    out: list[dict] = []
    seen_ids: set = set()
    base = BASE.format(barrio=barrio["slug"])
    for page in range(1, max_pages + 1):
        url = base + (f"?page={page}" if page > 1 else "")
        try:
            h = _fetch(url)
        except Exception as e:
            print(f"    ! Properati {barrio['nombre']} p{page}: {type(e).__name__}: {e}")
            break
        starts = [m.start() for m in ARTICLE_RE.finditer(h)]
        if not starts:
            break
        new_this_page = 0
        for i, start in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(h)
            chunk = h[start:end]
            listing = _parse_card(chunk, barrio["nombre"], barrios_cfg, features_cfg)
            if not listing or listing["id"] in seen_ids:
                continue
            seen_ids.add(listing["id"])
            out.append(listing)
            new_this_page += 1
        print(f"  Properati {barrio['nombre']:18} p{page}: {new_this_page} PHs (de {len(starts)} cards)")
        if new_this_page == 0 and page >= 2:
            break
        if len(starts) < 30:  # última página (menos de full page)
            break
        time.sleep(sleep)
    return out


def scrape_all(config: dict) -> list[dict]:
    src_cfg = config["sources"].get("properati", {})
    if not src_cfg.get("habilitado"):
        return []
    if cc_requests is None:
        print("  ! Properati deshabilitado: falta `curl_cffi`")
        return []

    sleep = max(config.get("sleep_between_requests", 0.5), 1.0)
    max_pages = src_cfg.get("max_pages", 3)
    features_cfg = config["feature_keywords"]
    barrios_cfg = config["barrios"]

    all_listings: list[dict] = []
    seen_ids: set = set()
    for b in barrios_cfg:
        for l in _scrape_barrio(b, barrios_cfg, features_cfg, max_pages, sleep):
            if l["id"] in seen_ids:
                continue
            seen_ids.add(l["id"])
            all_listings.append(l)

    return all_listings
