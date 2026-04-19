# Helen en CABA

Mini-site para presentar un relevamiento de PHs en alquiler en CABA a Helen, a partir del brief detallado en [`docs/brief.md`](./docs/brief.md).

Pensado como punto de partida iterativo: se arranca con una primera selección, Helen pide sacar/agregar, y el site se actualiza editando JSON.

## Ejecutar y listo

Solo necesitás **Python 3** (viene instalado en macOS / la mayoría de Linux).

```bash
cd site
python3 -m http.server 8000
# abrí http://localhost:8000
```

Eso es todo para ver el site. Para refrescar los datos desde Argenprop:

```bash
python3 scripts/scrape.py
```

### Si no tenés Python

- **macOS**: viene de fábrica. Probá `python3 --version`. Si no, instalá con [Homebrew](https://brew.sh): `brew install python`.
- **Linux**: `sudo apt install python3` (Debian/Ubuntu) · `sudo dnf install python3` (Fedora).
- **Windows**: descargá desde [python.org/downloads](https://www.python.org/downloads/) y tildá "Add Python to PATH" durante la instalación.

Verificar: `python3 --version` debería devolver `Python 3.x.x` (o `python --version` en Windows).

## Estructura del repo

```
docs/brief.md            brief (perfil, barrios, criterios, red flags, presupuesto)
CLAUDE.md                guía técnica para devs/agentes que sigan el proyecto
README.md                este archivo
site/
  index.html             UI
  styles.css
  app.js                 render + filtros (fetch de data.json)
  data.json              fuente única de datos (output del scraper)
scripts/
  config.json            barrios + sources + heurísticas
  scrape.py              orquestador: corre todos los sources, dedupe, escribe data.json
  scrape_argenprop.py    scraper HTML+regex de Argenprop (paginado)
  scrape_remax.py        scraper API JSON de Remax (paginado)
```

## Uso — filtros disponibles

Panel izquierdo:

- **Barrio** — chips multi-select, ordenados según la prioridad del brief. Si ninguno activo → muestra todos.
- **Precio (USD)** — rango min/máx. Los ARS se convierten a USD con tipo de cambio editable en `app.js` (`EXCHANGE_RATE`).
- **Ambientes (mín)** — 1+, 2+, 3+, 4+. Default **2+**.
- **Metros cubiertos (mín)** — 35, 50, 70, 100. Default **50+**.
- **Características** — patio, terraza, sin expensas, amoblado, reciclado, ★ apto mascotas, ★ PH al fondo (heurística).
- **Fuente** — Argenprop, etc. (se irán sumando).
- **Inmobiliaria** — input con autocomplete, matchea por substring.
- **Ocultar "solo uso comercial"** — prendido por default. Avisos "solo profesional / no apto vivienda" no sirven para vivir.
- **Orden** — precio USD asc/desc, metros desc, ambientes desc.

Marcas especiales en los cards:

- **★ Apto mascotas** (dorado) — el aviso lo declara explícitamente.
- **★ Al fondo** (verde) — el título/descripción menciona "al fondo", "contrafrente", "2do/3ro al fondo". Es heurística: **chequear en la visita**.

Cada card linkea al aviso original y al pasar el mouse sobre la foto cicla todas las imágenes del aviso.

## Tocar la config

Todo lo que la **búsqueda del scraper** hace está parametrizado en [`scripts/config.json`](./scripts/config.json). Editar y re-correr `python3 scripts/scrape.py`:

- **Habilitar/deshabilitar una fuente** → `sources.argenprop.habilitado` / `sources.remax.habilitado` (true/false).
- **Agregar/quitar un barrio** → editar el array `barrios`. Cada item: `{ "nombre": "X", "slug": "argenprop-slug", "prioridad": 1 }`. El `slug` es el que usa Argenprop en su URL (ej: `villa-crespo`); el `nombre` es el display y también lo que se matchea contra `geoLabel` de Remax.
- **Argenprop — máximo de páginas a scrapear por barrio** → `sources.argenprop.max_pages_per_barrio` (default 5). Si hay más stock, subir.
- **Remax — filtros del API** → `sources.remax.operation_id` (2 = alquiler), `type_id` (12 = PH). Ver `scrape_remax.py` para los IDs de otros tipos.
- **Cambiar las keywords** de detección de features (patio, terraza, al_fondo, etc.) → editar `feature_keywords`. Son case-insensitive, matchean por substring.
- **Agregar una feature nueva** → sumar una key a `feature_keywords` y después mostrarla/filtrarla en `site/app.js` (ver CLAUDE.md).
- **Cambiar el tipo de cambio ARS→USD** → editar `EXCHANGE_RATE` en `site/app.js` (default 1400).

## Workflow de iteración

Todo el estado vive en `site/data.json`. El scraper lo regenera, **preservando** cualquier campo `hidden` o `notes` de listings que hayas marcado.

### "Sacá este PH"

Agregar `"hidden": true` al objeto del listing en `site/data.json`. No se renderiza pero queda en el archivo. Sobrevive al siguiente `scrape.py`.

### "Agregá este otro que me pasaron" (dueño directo, grupo de FB, referido)

Objeto nuevo en `listings[]` con el schema de CLAUDE.md. Campos mínimos: `id`, `source`, `barrio`, `titulo`, `precio`, `moneda`, `url`.

### "Sumá más avisos del site X"

Hoy la data viene sólo de Argenprop. ZonaProp/MercadoLibre/Properati/ByT bloquean scraping automático (ver tabla en CLAUDE.md). Para sumar otra fuente automatizable, agregar un nuevo módulo en `scripts/` que respete el mismo schema de output.

### "Quiero filtrar por Y"

Ver `CLAUDE.md` → **Agregar un filtro nuevo**. Requiere tocar `index.html`, `app.js` y (si es una feature nueva a extraer) `scripts/config.json`.

## Fuentes actuales

- **Argenprop** — scraping HTML de `/ph/alquiler/{barrio}`, 10 barrios del brief. ~80 listings después de dedup.
- **Remax** — API JSON pública (Angular SPA). Paginado completo (todos los PH-rent de Argentina, filtrados client-side a los barrios del brief). ~12 listings después de dedup.

Los listings que aparecen en **ambas** fuentes (misma dirección) se muestran **una sola vez**, con una nota "También en X" debajo. La dedup es por `(calle, número-bucket-de-100, barrio)` — ver `property_key` en `scripts/scrape.py`.

## Para Helen

1. Abrí el site y jugá con los filtros.
2. Por cada PH que descartes, decime "sacá el de [dirección/barrio]" y lo oculto.
3. Los PHs marcados **Solo comercial** (badge rojo) están ocultos por default — son oficinas.
4. Tené a mano el checklist de [`docs/brief.md`](./docs/brief.md) al visitar: el site no sabe si la medianera es durlock, ni confirma "al fondo" (solo sospecha).
5. Precios: cada aviso en su moneda original + equivalente en USD abajo (conversión 1 USD = 1400 ARS).
