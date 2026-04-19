"""
Scraper de ZonaProp. Usa curl_cffi para emular TLS fingerprint de Chrome real
y pasar Cloudflare.

ZonaProp embebe toda la data de listings en `window.__PRELOADED_STATE__` como
JSON — extracción limpia, sin regex sobre HTML.

Entrypoint: scrape_all(config) -> list[dict]

Dependencia: curl_cffi (único source que necesita pip install — Cloudflare
no se pasa con urllib puro).
"""
from __future__ import annotations
import html as html_mod
import json
import re
import time

try:
    from curl_cffi import requests as cc_requests
except ImportError:
    cc_requests = None

URL_BASE = "https://www.zonaprop.com.ar/ph-alquiler-{barrios}.html"
# Paginación: agrega "-pagina-N" antes del .html
PRELOADED_RE = re.compile(
    r"window\.__PRELOADED_STATE__\s*=\s*(\{[\s\S]*?\});?\s*(?:</script|window\.)")


def _fetch(url: str) -> str:
    if cc_requests is None:
        raise RuntimeError(
            "ZonaProp requiere `curl_cffi` para pasar Cloudflare. "
            "Instalar con: pip3 install --break-system-packages curl_cffi"
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


def _int_or_none(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(str(v).replace(",", ".").split()[0]))
    except (ValueError, IndexError):
        return None


def _parse_price(price_ops: list) -> tuple[int | None, str | None]:
    """ZonaProp puede tener múltiples 'priceOperationTypes' (alquiler, venta, etc). Tomar el primero."""
    if not price_ops:
        return None, None
    # Find alquiler first, else take first
    for op in price_ops:
        op_type = (op.get("operationType") or {}).get("name", "").lower()
        if "alquiler" in op_type or "rent" in op_type:
            prices = op.get("prices") or []
            if prices:
                p = prices[0]
                return _int_or_none(p.get("amount")), p.get("currency")
    # fallback
    prices = (price_ops[0].get("prices") or [])
    if prices:
        p = prices[0]
        return _int_or_none(p.get("amount")), p.get("currency")
    return None, None


def _parse_m2(main_features: dict) -> tuple[int | None, int | None]:
    """mainFeatures devuelve {CFT2: {...value: 100 m² tot.}, CFT1: cubierta, ...}"""
    cubierta = None
    total = None
    for key, val in (main_features or {}).items():
        if not isinstance(val, dict):
            continue
        text = (val.get("value") or "").lower()
        if "cubier" in text:
            cubierta = _int_or_none(text)
        elif "tot" in text or "m² tot" in text:
            total = _int_or_none(text)
    return cubierta or total, None


def _parse_feature_number(main_features: dict, label: str) -> int | None:
    """Find a feature with label containing keyword (e.g., 'ambientes', 'dormitorios')."""
    for key, val in (main_features or {}).items():
        if not isinstance(val, dict):
            continue
        lbl = (val.get("label") or "").lower()
        if label in lbl:
            return _int_or_none(val.get("value"))
    return None


def _pick_barrio(posting_location: dict, barrios_cfg: list[dict]) -> str | None:
    """ZonaProp: postingLocation.location.name = 'Palermo'/'Colegiales'/etc."""
    import unicodedata
    def norm(s):
        return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn").strip()
    candidates: list[str] = []
    loc = posting_location.get("location")
    if isinstance(loc, dict):
        if isinstance(loc.get("name"), str):
            candidates.append(loc["name"])
        # también el parent por si el nombre del barrio vive un nivel arriba
        p = loc.get("parent")
        if isinstance(p, dict) and isinstance(p.get("name"), str):
            candidates.append(p["name"])
    # fallbacks
    for field in ("neighborhood", "subBarrio", "barrio", "zone", "city"):
        v = posting_location.get(field)
        if isinstance(v, str):
            candidates.append(v)
        elif isinstance(v, dict):
            candidates.append(v.get("name") or "")
    for c in candidates:
        n = norm(c)
        for b in barrios_cfg:
            if norm(b["nombre"]) == n:
                return b["nombre"]
    return None


def _parse_listing(p: dict, barrios_cfg: list[dict], features_cfg: dict) -> dict | None:
    posting_id = p.get("postingId") or p.get("postingCode")
    if not posting_id:
        return None

    titulo = _clean(p.get("generatedTitle") or p.get("title"))
    direccion = None
    loc = p.get("postingLocation") or {}
    addr = loc.get("address")
    if isinstance(addr, dict):
        direccion = _clean(addr.get("name") or addr.get("street"))
    elif isinstance(addr, str):
        direccion = _clean(addr)

    barrio = _pick_barrio(loc, barrios_cfg)
    if not barrio:
        return None  # fuera de los barrios del brief

    precio, moneda = _parse_price(p.get("priceOperationTypes") or [])

    expensas = _int_or_none((p.get("expenses") or {}).get("amount")) if isinstance(p.get("expenses"), dict) else _int_or_none(p.get("expenses"))

    mf = p.get("mainFeatures") or {}
    m2, _ = _parse_m2(mf)
    ambientes = _parse_feature_number(mf, "ambient")
    dormitorios = _parse_feature_number(mf, "dormitorio")
    if ambientes is None:
        ambientes = _int_or_none(p.get("ambiences"))
    if dormitorios is None:
        dormitorios = _int_or_none(p.get("rooms"))

    # Publisher (inmobiliaria)
    pub = p.get("publisher") or {}
    inmobiliaria = _clean(pub.get("name") if isinstance(pub, dict) else None)

    # Images — ZonaProp: visiblePictures.pictures[].url730x532 / url360x266
    imgs = []
    vp = p.get("visiblePictures") or {}
    pics = vp.get("pictures") if isinstance(vp, dict) else None
    if isinstance(pics, list):
        for pic in pics:
            if not isinstance(pic, dict):
                continue
            u = pic.get("url730x532") or pic.get("url360x266") or pic.get("url")
            if isinstance(u, str):
                imgs.append(u.split("?")[0])  # strip ?isFirstImage=true etc
    seen = set(); imgs = [u for u in imgs if not (u in seen or seen.add(u))]

    # URL (ZonaProp usa paths like /propiedades/clasificado/...-ID.html)
    url_field = p.get("url")
    if not url_field:
        slug = (titulo or "ph").lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")[:60]
        url_field = f"/propiedades/{slug}-{posting_id}.html"
    if url_field.startswith("/"):
        url_field = f"https://www.zonaprop.com.ar{url_field}"

    # Features heurística
    blob_parts = [titulo or "", _clean(p.get("description") or "") or ""]
    # flagsFeatures / generalFeatures (ZonaProp marca "amoblado" ahí)
    for fk in ("flagsFeatures", "generalFeatures", "highlightedFeatures", "developmentFeatures"):
        fv = p.get(fk)
        if isinstance(fv, dict):
            blob_parts.append(" ".join(str(v) for v in fv.values()))
        elif isinstance(fv, list):
            blob_parts.append(" ".join(str(v) for v in fv))
    blob = " ".join(blob_parts)
    features = _extract_features(blob, features_cfg)

    return {
        "id": f"zp-{posting_id}",
        "source": "ZonaProp",
        "inmobiliaria": inmobiliaria,
        "tipo_propiedad": "PH",
        "barrio": barrio,
        "titulo": titulo or "",
        "direccion": direccion,
        "precio": precio,
        "moneda": moneda,
        "periodo_dias": 30,
        "periodo_label": "mensual",
        "expensas": expensas,
        "m2": m2,
        "ambientes": ambientes,
        "dormitorios": dormitorios,
        "antiguedad": None,
        "url": url_field,
        "imagenes": imgs,
        "features": features,
    }


def _build_url(barrios_slugs: list[str], page: int) -> str:
    """ZonaProp une múltiples barrios con guion. URL larga = 410; chunkear a 7-8 barrios."""
    joined = "-".join(barrios_slugs)
    base = URL_BASE.format(barrios=joined)
    if page > 1:
        base = base.replace(".html", f"-pagina-{page}.html")
    return base


def _chunk(lst: list, n: int) -> list[list]:
    return [lst[i:i + n] for i in range(0, len(lst), n)]


def _scrape_chunk(barrios_chunk: list[str], barrios_cfg: list[dict], features_cfg: dict,
                   max_pages: int, sleep: float, chunk_label: str) -> list[dict]:
    all_listings: list[dict] = []
    seen_ids: set = set()
    total_pages_reported = None
    for page in range(1, max_pages + 1):
        url = _build_url(barrios_chunk, page)
        try:
            h = _fetch(url)
        except Exception as e:
            print(f"    ! ZonaProp [{chunk_label}] p{page}: {type(e).__name__}: {e}")
            break

        m = PRELOADED_RE.search(h)
        if not m:
            print(f"    ! ZonaProp [{chunk_label}] p{page}: no __PRELOADED_STATE__")
            break
        try:
            state = json.loads(m.group(1))
        except json.JSONDecodeError:
            break

        list_store = state.get("listStore") or {}
        postings = list_store.get("listPostings") or []
        paging = list_store.get("paging") or {}
        if total_pages_reported is None:
            print(f"  ZonaProp [{chunk_label}]: {paging.get('totalResults','?')} resultados / {paging.get('totalPages','?')} páginas")
            total_pages_reported = paging.get("totalPages")

        page_new = 0
        for p in postings:
            listing = _parse_listing(p, barrios_cfg, features_cfg)
            if not listing or listing["id"] in seen_ids:
                continue
            seen_ids.add(listing["id"])
            all_listings.append(listing)
            page_new += 1

        print(f"  ZonaProp [{chunk_label}] p{page}: {page_new} nuevos (de {len(postings)})")
        if not postings:
            break
        if total_pages_reported and page >= int(total_pages_reported):
            break
        time.sleep(sleep)
    return all_listings


def scrape_all(config: dict) -> list[dict]:
    src_cfg = config["sources"].get("zonaprop", {})
    if not src_cfg.get("habilitado"):
        return []
    if cc_requests is None:
        print("  ! ZonaProp deshabilitado: falta `curl_cffi` (pip3 install --break-system-packages curl_cffi)")
        return []

    sleep = max(config.get("sleep_between_requests", 0.5), 1.0)
    max_pages = src_cfg.get("max_pages", 10)
    chunk_size = src_cfg.get("barrios_per_url", 8)
    features_cfg = config["feature_keywords"]
    barrios_cfg = config["barrios"]
    # Usar solo slugs "padre" (sin sub-barrios como palermo-viejo que puede no existir en ZonaProp).
    # ZonaProp suele tener los principales. Si alguno da 404 el scraper sigue.
    # Dedup: usar sólo el slug base sin duplicar (palermo-hollywood no, palermo sí).
    # Regla simple: si un slug contiene otro más corto como prefix + "-", descartar el más largo.
    slugs = [b["slug"] for b in barrios_cfg]
    parents = set()
    for s in slugs:
        is_child = any(s != other and s.startswith(other + "-") for other in slugs)
        if not is_child:
            parents.add(s)
    slugs_dedup = [s for s in slugs if s in parents]

    chunks = _chunk(slugs_dedup, chunk_size)
    all_listings: list[dict] = []
    seen_ids: set = set()
    for i, chunk_slugs in enumerate(chunks):
        label = f"chunk {i+1}/{len(chunks)}"
        for l in _scrape_chunk(chunk_slugs, barrios_cfg, features_cfg, max_pages, sleep, label):
            if l["id"] in seen_ids:
                continue
            seen_ids.add(l["id"])
            all_listings.append(l)

    return all_listings
