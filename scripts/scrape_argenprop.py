"""
Scraper de Argenprop. Paginado. Stdlib only.

Entrypoint: scrape_all(config) -> list[dict] (schema unificado de listings).

Regex sobre HTML crudo. Si Argenprop cambia el markup, ajustar los patterns arriba.
"""
from __future__ import annotations
import html as html_mod
import re
import time
from urllib import request, error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Cada card abre con <a ... href="/ph-en-alquiler-..." ... class="card " ...>
CARD_START = re.compile(
    r'<a\s+href="(/ph-en-alquiler[^"]+)"[^>]*class="card\s"[^>]*>',
    re.IGNORECASE | re.DOTALL,
)
ATTR = re.compile(r'(\w[\w-]*)="([^"]*)"')
IMG = re.compile(r'(?:src|data-src)="(https://www\.argenprop\.com/static-content/[^"]+)"')
ADDRESS = re.compile(r'<p\s+class="card__address[^"]*"[^>]*>\s*([^<]+?)\s*</p>')
TITLE = re.compile(r'<h2[^>]*>\s*([^<]+?)\s*</h2>')
AGENT_ALT_IMG = re.compile(r'class="card__agent"[^>]*>[\s\S]*?<img[^>]*\balt="([^"]+)"')
EXPENSES = re.compile(r'card__expenses[^>]*>\s*\$?\s*([^<]+?)\s*<')
MAIN_FEATURES_BLOCK = re.compile(r'card__main-features[\s\S]*?</ul>')
LI = re.compile(r'<li[^>]*>([\s\S]*?)</li>')
ICON_RE = re.compile(r'basico1-icon-(\w+)')


def _fetch(url: str) -> str:
    req = request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "es-AR,es;q=0.9",
    })
    with request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = re.sub(r"<[^>]+>", "", s)
    s = html_mod.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _to_int(s: str | None) -> int | None:
    """Strip non-digits (para precios/expensas con separador de miles tipo '280.000')."""
    if not s:
        return None
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else None


def _first_int(s: str | None) -> int | None:
    """Primer grupo de dígitos (para m²/ambientes/dormitorios — '90.52 m²' → 90, '113 m²' → 113).
    Evita el bug de '90.52' → 9052 que tenía _to_int."""
    if not s:
        return None
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


def _extract_features(text: str, keywords: dict) -> dict:
    t = text.lower()
    return {feat: any(kw in t for kw in kws) for feat, kws in keywords.items()}


def _parse_card(chunk: str, barrio: str, features_cfg: dict) -> dict | None:
    m = CARD_START.search(chunk)
    if not m:
        return None
    href = m.group(1)
    opening = m.group(0)
    attrs = dict(ATTR.findall(opening))

    idaviso = attrs.get("idaviso") or attrs.get("data-item-card") or href.rsplit("--", 1)[-1]
    idmoneda = attrs.get("idmoneda", "")
    moneda = "ARS" if idmoneda == "1" else "USD" if idmoneda == "2" else None
    precio = _to_int(attrs.get("montooperacion"))
    ambientes = _to_int(attrs.get("ambientes"))
    dormitorios = _to_int(attrs.get("dormitorios"))

    titulo = _clean(TITLE.search(chunk).group(1)) if TITLE.search(chunk) else None
    direccion = _clean(ADDRESS.search(chunk).group(1)) if ADDRESS.search(chunk) else None

    agent_m = AGENT_ALT_IMG.search(chunk)
    inmobiliaria = _clean(agent_m.group(1)) if agent_m else None

    expensas = None
    exp_m = EXPENSES.search(chunk)
    if exp_m:
        raw = _clean(exp_m.group(1)) or ""
        raw_low = raw.lower()
        if "sin" in raw_low or "no paga" in raw_low:
            expensas = 0
        else:
            expensas = _to_int(raw)

    m2 = None
    antiguedad = None
    mf = MAIN_FEATURES_BLOCK.search(chunk)
    if mf:
        for li_m in LI.finditer(mf.group(0)):
            li_html = li_m.group(1)
            icon_m = ICON_RE.search(li_html)
            icon = icon_m.group(1) if icon_m else ""
            text = (_clean(li_html) or "").lower()
            if icon == "superficie_cubierta" or "m²" in text or " m2" in text:
                if m2 is None:
                    m2 = _first_int(text)
            elif icon == "cantidad_dormitorios" and dormitorios is None:
                dormitorios = _first_int(text)
            elif icon == "cantidad_ambientes" and ambientes is None:
                ambientes = _first_int(text)
            elif icon == "antiguedad":
                antiguedad = _clean(li_html)

    imagenes: list[str] = []
    seen: set[str] = set()
    for im in IMG.finditer(chunk):
        u = im.group(1)
        if u not in seen:
            seen.add(u)
            imagenes.append(u)

    features = _extract_features(_clean(chunk) or "", features_cfg)

    return {
        "id": f"ap-{idaviso}",
        "source": "Argenprop",
        "inmobiliaria": inmobiliaria,
        "tipo_propiedad": "PH",  # URL filtra por PH
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
        "antiguedad": antiguedad,
        "url": f"https://www.argenprop.com{href}",
        "imagenes": imagenes,
        "features": features,
    }


def _parse_page(html: str, barrio: str, features_cfg: dict) -> list[dict]:
    out: list[dict] = []
    starts = [m.start() for m in CARD_START.finditer(html)]
    if not starts:
        return out
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(html)
        listing = _parse_card(html[start:end], barrio, features_cfg)
        if listing:
            out.append(listing)
    return out


def scrape_all(config: dict) -> list[dict]:
    """Entrypoint."""
    src_cfg = config["sources"]["argenprop"]
    if not src_cfg.get("habilitado"):
        return []
    base_url = src_cfg["base_url"]
    max_pages = src_cfg.get("max_pages_per_barrio", 5)
    pag_param = src_cfg.get("pagina_param", "pagina")
    sleep = config.get("sleep_between_requests", 0.5)
    features_cfg = config["feature_keywords"]

    all_listings: list[dict] = []
    seen_urls: set[str] = set()

    for b in config["barrios"]:
        barrio, slug = b["nombre"], b["slug"]
        listings_barrio = 0
        for page in range(1, max_pages + 1):
            url = base_url.replace("{slug}", slug)
            if page > 1:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}{pag_param}={page}"
            try:
                html = _fetch(url)
            except error.HTTPError as e:
                print(f"    ! Argenprop {barrio} p{page}: HTTP {e.code}")
                break
            except Exception as e:
                print(f"    ! Argenprop {barrio} p{page}: {type(e).__name__}: {e}")
                break
            page_listings = _parse_page(html, barrio, features_cfg)
            if not page_listings:
                break  # no hay más páginas
            new = 0
            for l in page_listings:
                if l["url"] not in seen_urls:
                    seen_urls.add(l["url"])
                    all_listings.append(l)
                    new += 1
            listings_barrio += new
            # si esta página trajo 0 listings nuevos, corta (último page o duplicado infinito)
            if new == 0:
                break
            time.sleep(sleep)
        print(f"  Argenprop {barrio:15} → {listings_barrio} listings")

    return all_listings
