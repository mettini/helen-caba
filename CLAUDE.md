# CLAUDE.md — contexto técnico del proyecto

Este repo arma un mini-site de relevamiento de PHs en alquiler en CABA para una búsqueda específica (ver `helen_caba.md` — brief con perfil, barrios, criterios). Este archivo es la referencia técnica: cómo está hecho, cómo extenderlo, qué decisiones se tomaron y por qué.

## El brief manda

Antes de tocar código, leer `helen_caba.md`. Todo el modelado (qué filtros, qué features se extraen, qué se oculta por default) sale de ahí. Ejemplos:

- `hideComercial` prendido por default → el brief pide vivienda + estudio de grabación, no oficina.
- Feature `al_fondo` es **heurística** (palabras clave en el aviso) — el brief aclara que hay que chequearlo en visita.
- Defaults del UI: 2 amb+ y 50 m²+ (Helen graba con monitores, necesita espacio).
- No se filtra por "depto" → el brief descarta deptos de entrada.

Si el brief cambia, los defaults del site deberían cambiar con él.

## Arquitectura

**Stack mínimo**: Python 3 (stdlib) + vanilla JS. Sin Node, sin framework, sin build step, sin `pip install`.

```
helen_caba.md              brief
README.md                  instrucciones de uso
CLAUDE.md                  esto
.gitignore
site/                      static site — se sirve con `python3 -m http.server`
  index.html
  styles.css
  app.js                   render + filtros, lee data.json
  data.json                fuente única de datos (output del scraper)
scripts/
  config.json              barrios + sources + heurísticas editables
  scrape.py                orquestador: corre todos los sources habilitados, dedupe, merge, escribe data.json
  scrape_argenprop.py      HTML + regex (paginado por barrio)
  scrape_remax.py          API JSON Angular (paginado global, filtro CABA + barrios)
```

Serve: `cd site && python3 -m http.server 8000` → `http://localhost:8000`.

No funciona con `file://` directo porque `fetch('data.json')` es bloqueado por CORS.

### Por qué este stack

- Python ya es necesario para el scraper. Sumar Zola/Node sería otra instalación → más fricción para quien haga `git clone && correr`.
- `http.server` es un módulo stdlib — cero dependencias adicionales.
- Vanilla JS y `fetch('data.json')` al runtime — el archivo de datos es la fuente de verdad, sin pipeline intermedio.
- Sin pip install → reproducible con cualquier Python 3 (macOS/Linux incluyen uno por default).

Si el proyecto crece (auth, múltiples usuarios, histórico) habría que migrar — hoy no se justifica.

## Schema de `site/data.json`

```jsonc
{
  "generatedAt": "2026-04-19",
  "sources": ["Argenprop"],
  "listings": [
    {
      "id": "ap-19453100",          // "<prefix>-<id>". Prefijo por source.
      "source": "Argenprop",         // display name
      "inmobiliaria": "…" | null,    // de alt= del logo del agente
      "barrio": "Colegiales",        // canonical — ver lista abajo
      "titulo": "…",
      "direccion": "…" | null,
      "precio": 1690000,             // número, sin símbolos
      "moneda": "ARS" | "USD",
      "expensas": 280000 | 0 | null, // 0 = sin expensas, null = no dice
      "m2": 113 | null,
      "ambientes": 3 | null,         // Argenprop manda muchos con null — ver fallback
      "dormitorios": 2 | null,
      "antiguedad": "A Estrenar" | null,
      "url": "https://www.argenprop.com/…",
      "imagenes": ["https://…", "…"],
      "features": {
        "patio": bool,
        "terraza": bool,
        "sin_expensas": bool,
        "amoblado": bool,
        "pet_friendly": bool,
        "reciclado": bool,
        "al_fondo": bool,            // heurística por keywords — ver config.json
        "solo_comercial": bool
      },
      "hidden": false,               // opcional. True → no renderizar.
      "notes": "",                   // opcional. Notas manuales post-visita/llamada.
      "property_key": "alvarez-thomas-900-colegiales", // generado por orquestador para dedup
      "also_in_sources": [           // opcional. Se renderiza como "También en X" en la card.
        { "source": "Remax", "url": "https://...", "inmobiliaria": "..." }
      ]
    }
  ]
}
```

### Barrios canónicos

Usar estos strings exactos (mapean a gradients en CSS y ordenamiento en JS):

`Chacarita`, `Colegiales`, `Villa Crespo`, `Villa Ortúzar`, `Parque Chas`, `Palermo`, `Palermo Soho`, `Palermo Hollywood`, `Palermo Botánico`, `Almagro`, `Caballito`, `Belgrano`, `Belgrano R`, `Belgrano C`, `Núñez`.

El mapeo a gradient se hace por `includes()` del slug en `app.js` (`bgClass()`), así sub-barrios de Palermo caen en `bg-palermo`. El orden de la lista de chips en el UI sigue `BARRIOS_BRIEF_ORDER` en `app.js`.

### Ambientes fallback

Argenprop devuelve `ambientes=""` (vacío) para muchos avisos porque solo cargan dormitorios. En el filtro usamos `ambientes ?? (dormitorios + 1)` como proxy: "2 dormitorios" ≈ "3 ambientes". Es aproximado pero evita descartar avisos válidos.

## Scrapers — cómo funciona

### Orquestador (`scripts/scrape.py`)

1. Lee `scripts/config.json`.
2. Por cada source habilitado (`config.sources.*.habilitado: true`), llama su `scrape_all(config) -> list[dict]`.
3. Cada listing se chequea contra:
   - **`id` técnico** (ej: `ap-19453100`, `rx-542244`) — evita duplicar dentro del mismo source.
   - **`property_key`** lógica: `calle + (número // 100) * 100 + barrio` normalizado. Matchea avisos del mismo inmueble en distintos sources (y a veces republicados en el mismo source).
4. Al encontrar un duplicado, la PRIMERA aparición queda como "primary" y se le suma un item a `also_in_sources: [{source, url, inmobiliaria}]`. Las duplicadas NO se agregan al output.
5. Preserva `hidden` y `notes` de listings previos (matching por URL exacta).
6. Escribe `site/data.json`.

**Sumar un source nuevo**: crear `scripts/scrape_<nombre>.py` que exporte `scrape_all(config) -> list[dict]`, importarlo en `scrape.py` y sumarlo al tuple `SOURCES`. Agregar el bloque correspondiente en `config.json` → `sources.<nombre>`.

### Argenprop (`scripts/scrape_argenprop.py`)

- **Método**: HTML crudo + regex.
- **Paginación**: `?pagina=N` hasta `max_pages_per_barrio` (config) o hasta que una página no traiga listings nuevos.
- **Observado abril 2026**: para muchos barrios `?pagina=2+` devuelve el mismo contenido de la página 1 — es decir, **el stock real está en la primera página**. La lógica de corte por "0 listings nuevos" evita scrapear de más.
- **Regex clave** al tope del archivo: `CARD_START`, `TITLE`, `ADDRESS`, `AGENT_ALT_IMG`, `EXPENSES`, `MAIN_FEATURES_BLOCK`, `IMG`. Si Argenprop cambia el markup, ajustar 1-2 regex.
- **Debug tip**: guardar un fetch en `/tmp/x.html` y correr `python3` interactivo.

### Remax (`scripts/scrape_remax.py`)

- **Método**: API JSON pública (Remax es Angular SPA, el HTML está vacío — la data viene del API).
- **Endpoint**: `https://api-ar.redremax.com/remaxweb-ar/api/listings/findAllWithEntrepreneurships`
- **Filtros** (URL query): `in=operationId:2` (alquiler) + `in=typeId:12` (PH). Ver `scrape_remax.py` para otros IDs (casa=9, depto=4, etc.).
- **Paginación**: `page=N&pageSize=50`. Abril 2026 hay 240 PH-rent en toda Argentina, 5 páginas.
- **Filtro de barrio**: post-scrape, matcheando `geoLabel.split(",")[0]` contra los barrios canónicos del config (normalizando tildes). Así solo quedan los de CABA + listados en el brief. En abril 2026: 59 CABA / 240 AR total, de los cuales ~17 en barrios del brief.
- **Imágenes**: la API devuelve `rawValue` tipo `"listings/{entityId}/{filename}"`. Se construye la URL final como `{image_cdn}listings/{entityId}/{size}/{filename}{ext}` (ver config). Tamaño default `360x200` en `.webp`.

## Acciones comunes (paso a paso)

### Ocultar un listado

1. Buscar el listing en `site/data.json` por `id` o URL.
2. Setear `"hidden": true` (o agregar el campo).
3. Guardar. Al refrescar el site no se muestra. Sobrevive a `scrape.py` porque se preserva.

### Agregar un listing manualmente (dueño directo, grupo de FB, referido)

Editar `site/data.json`, agregar un objeto al array `listings`:

```json
{
  "id": "manual-colegiales-teodoro-200",
  "source": "Manual",
  "inmobiliaria": null,
  "barrio": "Colegiales",
  "titulo": "...",
  "direccion": "Teodoro García 200",
  "precio": 950000,
  "moneda": "ARS",
  "expensas": 0,
  "m2": 55,
  "ambientes": 3,
  "dormitorios": 2,
  "url": "https://facebook.com/marketplace/item/…",
  "imagenes": [],
  "features": { "patio": true, "terraza": false, "sin_expensas": true, "amoblado": false, "pet_friendly": false, "reciclado": false, "al_fondo": true, "solo_comercial": false }
}
```

Convención de `id`: `manual-<slug>`, `fb-<slug>`, etc. — lo que sea, que no colisione con `ap-*`.

### Agregar un nuevo barrio al scraper

Editar `scripts/config.json`, sumar al array `barrios`:

```json
{ "nombre": "Saavedra", "slug": "saavedra", "prioridad": 5 }
```

Después `python3 scripts/scrape.py`. Si el nuevo barrio no está en `BARRIOS_BRIEF_ORDER` (`app.js`) se muestra al final alfabéticamente. Si querés ordenarlo, agregalo al array.

### Agregar un nuevo source scrape-able (ej: MercadoLibre, Properati)

Hoy solo Argenprop pasa WebFetch/curl directo. Para sumar otro:

1. Crear `scripts/scrape_<source>.py` siguiendo el mismo patrón (regex sobre HTML crudo, output listings en el schema).
2. Agregar al `scripts/config.json` en `sources` con `habilitado: true`.
3. Modificar `scripts/scrape.py` (o crear un orquestador) para correr todos los sources habilitados y mergear sus outputs en `data.json`. Prefijar IDs con `<source>-` para evitar colisiones.
4. (Opcional) Agregar un color de badge distinto en `styles.css` para la source.

Si el site tiene Cloudflare (como ZonaProp) → `curl` devuelve 403. Alternativas: Playwright/Selenium local (out of scope hoy), scraping manual con copy/paste, pedirle al dueño.

### Agregar un filtro nuevo (ej: "años de construcción")

1. **Config** (`scripts/config.json`): si la feature se detecta por keywords, agregarla a `feature_keywords`. Si es un campo numérico (ej: `anio_construccion`), sumar la extracción en `scrape.py`.
2. **Data**: asegurate que `data.json` tenga el campo (re-correr scraper).
3. **HTML** (`site/index.html`): agregar el control en `<aside class="filters">`. Para boolean `data-feat="…"`. Para numérico, un input con `id` propio.
4. **JS** (`site/app.js`):
   - Sumar al `state.filters`.
   - Bindear el control en `bindControls()`.
   - Sumar la condición en `matches()`.
   - Agregar reset en `#resetBtn`.
5. **Chip** en las cards (opcional): agregarlo a `featChips()`.

### Cambiar el tipo de cambio ARS→USD

Editar `EXCHANGE_RATE` en `site/app.js` (constante al tope del archivo). El scraper no lo usa — es solo para el filtro/sort del frontend.

### Acción bulk vía jq

```bash
# ocultar todos los comerciales de Caballito
jq '.listings |= map(if .barrio == "Caballito" and .features.solo_comercial then .hidden = true else . end)' \
  site/data.json > site/data.json.tmp && mv site/data.json.tmp site/data.json
```

## Sources investigados (abril 2026)

| Source | Estado scrape | Nota |
|---|---|---|
| **Argenprop** | ✅ funciona | curl + regex. Paginado. |
| **Remax** | ✅ funciona | API JSON Angular. Paginado completo. ~60 PH-rent CABA / 240 AR. |
| **ZonaProp** | ❌ 403 Cloudflare | Mayor volumen del mercado. Requiere navegador real. |
| **MercadoLibre Inmuebles** | ❌ 403 | Bloqueo similar. |
| **Properati** | ❌ 403 | Bloqueo similar. |
| **ByT Argentina** | ❌ redirect loop | Temporarios amoblados. URL base podría cambiarse. |
| **Apartments BA / Stay in BA / Oh My Flat** | no probado | Temporarios expat. Siguiente fuente candidata. |
| **Inmobusqueda** | no probado | Agregador. |
| **Grupos de Facebook** | no scrape-able | Requieren login. Entrada manual. |

Estrategia si hay que desbloquear: Playwright local o una pasada manual. No vale la pena para la primera ronda con Argenprop.

## Decisiones de diseño

- **Imágenes por hotlink** a Argenprop (`https://www.argenprop.com/static-content/…`). Cargan sin `Referer`. Si en algún momento bloquean, opciones: descargar localmente a `site/img/` y actualizar URLs, o proxy.
- **Fallback visual**: si el listing no tiene `imagenes[]`, se muestra gradient por barrio + inicial serif. Ningún card sale roto.
- **Carousel on-hover**: `setInterval(800ms)` cicla `img.src` mientras el mouse está sobre el card. Sin fade (evita saltos), los dots abajo indican posición. Al `mouseleave` vuelve a índice 0.
- **Precio en moneda original + equivalente USD**. El filtro trabaja sobre USD-equivalent (conversión 1400 editable). No se toca el display — Helen ve lo que publicó el aviso.
- **Ambientes fallback por dormitorios + 1**. Muchos avisos tienen `ambientes=""`. Sin fallback, el filtro "2+" les saca; con fallback aparecen.
- **Sub-barrios como strings distintos** (Palermo Soho, Belgrano R). Permite filtrar granular. Al hacer "Barrio = Palermo" NO matchea Palermo Soho — es intencional (si querés lo cambiamos a match por prefijo).
- **`features` como objeto**, no array. Filtros O(1), schema explícito. Sumar una feature = sumar una key.
- **Dedup cross-source** por `property_key = calle + (num//100)*100 + barrio` (ver `scrape.py`). El bucket de 100 matchea "Álvarez Thomas 900" con "Álvarez Thomas 920" — probablemente mismo edificio / PH del mismo pasillo. Si genera falsos positivos, achicar el bucket a 10 o 1. Si hace falta más finura, trackear bucket + desviación máxima.

## Ideas para la próxima vuelta

- Sumar fuentes temporarias amobladas (Apartments BA, Stay in BA, Oh My Flat).
- Vista mapa (Leaflet) con geocoding de las direcciones.
- Campo de notas editable en la UI con persistencia a `data.json` vía server endpoint (romper el modelo pure-static).
- Tipo de cambio en vivo (dolarhoy API).
- Dedupe automático de listings que aparecen en varias fuentes (match aproximado por dirección).
- Paginación si el volumen crece > 200 listings.
