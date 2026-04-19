"""
Scraper de Remax. Usa la API JSON pública (Angular SPA).

API:
  GET https://api-ar.redremax.com/remaxweb-ar/api/listings/findAllWithEntrepreneurships
      ?page=N&pageSize=50&sort=-createdAt&in=operationId:2&in=typeId:12

Entrypoint: scrape_all(config) -> list[dict] (schema unificado de listings).
"""
from __future__ import annotations
import html as html_mod
import json
import re
import time
import unicodedata
from urllib import request, error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _norm(s: str) -> str:
    return _strip_accents((s or "").strip().lower())


def _fetch_json(url: str) -> dict:
    req = request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _photo_url(raw_value: str, cdn: str, size: str, ext: str) -> str | None:
    """Convierte 'listings/{entity}/{file}' → '{cdn}listings/{entity}/{size}/{file}{ext}'."""
    parts = raw_value.split("/")
    if len(parts) < 3:
        return None
    prefix = "/".join(parts[:-1])
    filename = parts[-1]
    return f"{cdn}{prefix}/{size}/{filename}{ext}"


def _barrio_match(geo_label: str, barrios_canonical: list[dict]) -> str | None:
    """Devuelve el nombre canónico si matchea alguno de los barrios del config.
    geoLabel tipo 'Colegiales, Capital Federal' o 'Nuñez, Capital Federal'."""
    if not geo_label:
        return None
    primer = geo_label.split(",")[0]
    if not primer:
        return None
    n = _norm(primer)
    for b in barrios_canonical:
        if _norm(b["nombre"]) == n:
            return b["nombre"]
        # matching parcial para sub-barrios (ej: "Palermo Soho" contiene "palermo")
        # pero solo para los explícitamente listados en barrios_canonical
    return None


def _clean_html(s: str | None) -> str | None:
    if s is None:
        return None
    s = re.sub(r"<[^>]+>", "", s)
    s = html_mod.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _extract_features(text: str, keywords: dict) -> dict:
    t = text.lower()
    return {feat: any(kw in t for kw in kws) for feat, kws in keywords.items()}


def _normalize(listing: dict, barrio: str, src_cfg: dict, features_cfg: dict) -> dict | None:
    try:
        lid = listing.get("id")
        if not lid:
            return None
        slug = listing.get("slug") or ""
        url = f"{src_cfg['listing_url_prefix']}{slug}"

        currency = (listing.get("currency") or {}).get("value", "").upper()
        moneda = "USD" if currency == "USD" else "ARS" if currency == "ARS" else None
        price = listing.get("price")
        precio = int(price) if price is not None else None
        exp_price = listing.get("expensesPrice")
        expensas = int(exp_price) if exp_price else (0 if exp_price == 0 else None)

        ambientes = listing.get("totalRooms")
        dormitorios = listing.get("bedrooms")
        m2 = listing.get("dimensionCovered") or listing.get("dimensionTotalBuilt")
        if m2 is not None:
            m2 = int(m2)

        direccion = _clean_html(listing.get("displayAddress"))
        titulo = _clean_html(listing.get("title"))
        inmobiliaria = ((listing.get("associate") or {}).get("officeName"))

        # Imágenes
        photos = listing.get("photos") or []
        imgs = []
        for p in photos:
            raw = (p or {}).get("rawValue")
            if not raw:
                continue
            u = _photo_url(raw, src_cfg["image_cdn"], src_cfg["image_size_suffix"], src_cfg["image_ext"])
            if u:
                imgs.append(u)

        # Features sobre título + descripción + dirección + subtipo
        descripcion = _clean_html(listing.get("description")) or ""
        blob = " ".join(filter(None, [titulo, descripcion, direccion, inmobiliaria]))
        features = _extract_features(blob, features_cfg)

        # typeId 12 = PH; otros (4=depto, 9=casa, etc.) se mapean a string legible
        remax_type = (listing.get("type") or {}).get("value", "").lower()
        tipo_map = {"ph": "PH", "casa": "Casa", "departamento_estandar": "Depto",
                    "departamento_monoambiente": "Depto", "departamento_semipiso": "Depto",
                    "departamento_duplex": "Depto", "departamento_triplex": "Depto"}
        tipo_propiedad = tipo_map.get(remax_type, remax_type.replace("_", " ").title() or "?")

        return {
            "id": f"rx-{lid}",
            "source": "Remax",
            "inmobiliaria": inmobiliaria,
            "tipo_propiedad": tipo_propiedad,
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
            "url": url,
            "imagenes": imgs,
            "features": features,
        }
    except Exception as e:
        print(f"    ! normalize failed: {e}")
        return None


def _scrape_pass(api: str, op_id: int, type_id: int | None, page_size: int,
                 sleep: float, src_cfg: dict, features_cfg: dict,
                 barrios_cfg: list, force_amoblado: bool, label: str) -> list[dict]:
    """Una pasada al API con filtros dados. Paginado completo."""
    all_listings: list[dict] = []
    seen_ids: set = set()
    page = 0
    total_pages = None
    total_items = None
    caba_count = 0
    while True:
        url = f"{api}?page={page}&pageSize={page_size}&sort=-createdAt&in=operationId:{op_id}"
        if type_id is not None:
            url += f"&in=typeId:{type_id}"
        try:
            resp = _fetch_json(url)
        except error.HTTPError as e:
            print(f"    ! Remax [{label}] p{page}: HTTP {e.code}")
            break
        except Exception as e:
            print(f"    ! Remax [{label}] p{page}: {type(e).__name__}: {e}")
            break

        body = resp.get("data") or {}
        items = body.get("data") or []
        if total_items is None:
            total_items = body.get("totalItems", 0)
            total_pages = body.get("totalPages", 0)
            print(f"  Remax [{label}]: {total_items} total (Argentina), {total_pages} páginas.")
        if not items:
            break

        for it in items:
            geo = it.get("geoLabel") or ""
            if "Capital Federal" not in geo:
                continue
            caba_count += 1
            barrio = _barrio_match(geo, barrios_cfg)
            if not barrio:
                continue
            norm = _normalize(it, barrio, src_cfg, features_cfg)
            if not norm or norm["id"] in seen_ids:
                continue
            if force_amoblado:
                norm["features"]["amoblado"] = True
            seen_ids.add(norm["id"])
            all_listings.append(norm)

        page += 1
        if total_pages and page >= total_pages:
            break
        time.sleep(sleep)

    from collections import Counter
    c = Counter(l["barrio"] for l in all_listings)
    print(f"  Remax [{label}] CABA en barrios del brief: {len(all_listings)} (de {caba_count} CABA totales)")
    for b, n in sorted(c.items(), key=lambda x: -x[1]):
        print(f"    {b:18} → {n}")
    return all_listings


def scrape_all(config: dict) -> list[dict]:
    src_cfg = config["sources"]["remax"]
    if not src_cfg.get("habilitado"):
        return []
    api = src_cfg["api_url"]
    page_size = src_cfg.get("page_size", 50)
    sleep = config.get("sleep_between_requests", 0.5)
    features_cfg = config["feature_keywords"]
    barrios_cfg = config["barrios"]

    # Pass 1: PH + alquiler tradicional (brief exige PH)
    p1 = _scrape_pass(api, src_cfg["operation_id"], src_cfg["type_id"],
                      page_size, sleep, src_cfg, features_cfg, barrios_cfg,
                      force_amoblado=False, label="PH rent")

    # Pass 2: temporal TODOS los tipos (PH + Depto + Casa). "temporal" = amoblado por default.
    # El UI tiene filtro `tipo_propiedad` con "PH" seleccionado por default, así los Deptos
    # quedan ocultos hasta que Helen destilde el filtro si está evaluando pre-residencia.
    p2 = _scrape_pass(api, 3, None, page_size, sleep, src_cfg, features_cfg,
                      barrios_cfg, force_amoblado=True, label="temporal (amoblado, todos los tipos)")

    by_id: dict[str, dict] = {l["id"]: l for l in p1}
    for l in p2:
        if l["id"] not in by_id:
            by_id[l["id"]] = l
    return list(by_id.values())
