// Helen en CABA — mini-site de relevamiento de PHs.
// Static site, vanilla JS, lee data.json.
// Ver CLAUDE.md y README.md para cómo extender / tocar la config.

// ========== Tipo de cambio — editá este número cuando cambie ==========
// Se usa para normalizar precios ARS a USD en el filtro "Precio" y sort por precio.
// Regla: precio_usd = moneda === 'USD' ? precio : precio / EXCHANGE_RATE
const EXCHANGE_RATE = 1400; // ARS por USD
// =======================================================================

const BARRIOS_BRIEF_ORDER = [
  // 1ra línea — pegados a Palermo, con stock de PHs
  'Chacarita', 'Colegiales', 'Villa Crespo',
  // 2da — escalón tranquilo
  'Villa Ortúzar', 'Parque Chas',
  // 3ra — continuidad Olivos + mejor perfil acústico (bumped up from 5th)
  'Belgrano', 'Belgrano R', 'Belgrano C', 'Núñez',
  // 4ta — Palermo (opción B)
  'Palermo', 'Palermo Soho', 'Palermo Hollywood', 'Palermo Botánico', 'Palermo Viejo',
  // 5ta — más lejos del eje
  'Almagro', 'Caballito', 'Saavedra',
];

const state = {
  listings: [],
  barrios: [],
  sources: [],
  tipos: [],
  filters: {
    barrios: new Set(),
    sources: new Set(),
    tipos: new Set(['PH']),  // brief = PH por default; destildar para ver Deptos/temporarios
    inmobiliaria: '',
    priceMin: null,
    priceMax: null,
    ambientesMin: 2,
    m2Min: 50,
    features: new Set(['amoblado']),
    hideComercial: true,
  },
  sort: 'price-asc',
};

// Precio mensual equivalente en USD. Normaliza moneda y período del aviso.
// Argenprop/Remax → periodo_dias=30 (mensual). Airbnb → puede ser 1, 5, 7, 30.
const usdOf = (l) => {
  if (l.precio == null) return null;
  const pd = l.periodo_dias || 30;
  const mensualOriginalMoneda = (l.precio * 30) / pd;
  return l.moneda === 'USD'
    ? Math.round(mensualOriginalMoneda)
    : Math.round(mensualOriginalMoneda / EXCHANGE_RATE);
};

const barrioSlug = (name) => (name || '').toLowerCase()
  .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

const bgClass = (barrio) => {
  const slug = barrioSlug(barrio);
  if (slug.includes('chacarita')) return 'bg-chacarita';
  if (slug.includes('colegiales')) return 'bg-colegiales';
  if (slug.includes('villa-crespo')) return 'bg-villa-crespo';
  if (slug.includes('palermo')) return 'bg-palermo';
  if (slug.includes('villa-ortuzar')) return 'bg-villa-ortuzar';
  if (slug.includes('parque-chas')) return 'bg-parque-chas';
  if (slug.includes('almagro')) return 'bg-almagro';
  if (slug.includes('caballito')) return 'bg-caballito';
  if (slug.includes('belgrano')) return 'bg-belgrano';
  if (slug.includes('nunez')) return 'bg-nunez';
  return 'bg-default';
};

const fmtPrice = (n, moneda) => {
  if (n == null) return '—';
  if (moneda === 'USD') return `USD ${n.toLocaleString('es-AR')}`;
  return `$ ${n.toLocaleString('es-AR')}`;
};
const fmtInt = (n) => (n == null ? '—' : n);
const escape = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
  ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));

// -------- Data --------
async function loadData() {
  const res = await fetch('data.json');
  const data = await res.json();
  state.listings = (data.listings || []).filter((l) => !l.hidden);

  const bCount = new Map();
  for (const l of state.listings) bCount.set(l.barrio, (bCount.get(l.barrio) || 0) + 1);
  state.barrios = [...bCount.entries()].map(([name, count]) => ({ name, count })).sort((a, b) => {
    const ia = BARRIOS_BRIEF_ORDER.indexOf(a.name);
    const ib = BARRIOS_BRIEF_ORDER.indexOf(b.name);
    if (ia !== -1 || ib !== -1) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    return a.name.localeCompare(b.name);
  });

  const sCount = new Map();
  for (const l of state.listings) sCount.set(l.source, (sCount.get(l.source) || 0) + 1);
  state.sources = [...sCount.entries()].map(([name, count]) => ({ name, count }));

  const tCount = new Map();
  for (const l of state.listings) tCount.set(l.tipo_propiedad || '?', (tCount.get(l.tipo_propiedad || '?') || 0) + 1);
  state.tipos = [...tCount.entries()]
    .sort((a, b) => (a[0] === 'PH' ? -1 : b[0] === 'PH' ? 1 : b[1] - a[1]))
    .map(([name, count]) => ({ name, count }));

  const d = new Date(data.generatedAt || Date.now());
  document.getElementById('generatedAt').textContent =
    d.toLocaleDateString('es-AR', { day: '2-digit', month: 'long', year: 'numeric' });
  document.getElementById('generatedSources').textContent = (data.sources || ['Argenprop']).join(', ');
  document.getElementById('exchangeRateDisplay').textContent = `${EXCHANGE_RATE.toLocaleString('es-AR')} ARS/USD`;
}

// -------- Render filter controls --------
function renderBarrioChips() {
  const el = document.getElementById('filterBarrios');
  el.innerHTML = state.barrios.map(({ name, count }) => `
    <button type="button" class="chip" data-barrio="${escape(name)}">
      ${escape(name)}<span class="chip-count">${count}</span>
    </button>`).join('');
  el.querySelectorAll('.chip').forEach((btn) => {
    btn.addEventListener('click', () => {
      const b = btn.dataset.barrio;
      if (state.filters.barrios.has(b)) state.filters.barrios.delete(b);
      else state.filters.barrios.add(b);
      btn.classList.toggle('is-active');
      render();
    });
  });
}

function renderSourceChips() {
  const el = document.getElementById('filterSources');
  el.innerHTML = state.sources.map(({ name, count }) => `
    <button type="button" class="chip" data-source="${escape(name)}">
      ${escape(name)}<span class="chip-count">${count}</span>
    </button>`).join('');
  el.querySelectorAll('.chip').forEach((btn) => {
    btn.addEventListener('click', () => {
      const s = btn.dataset.source;
      if (state.filters.sources.has(s)) state.filters.sources.delete(s);
      else state.filters.sources.add(s);
      btn.classList.toggle('is-active');
      render();
    });
  });
}

function renderTipoChips() {
  const el = document.getElementById('filterTipos');
  el.innerHTML = state.tipos.map(({ name, count }) => `
    <button type="button" class="chip ${state.filters.tipos.has(name) ? 'is-active' : ''}" data-tipo="${escape(name)}">
      ${escape(name)}<span class="chip-count">${count}</span>
    </button>`).join('');
  el.querySelectorAll('.chip').forEach((btn) => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.tipo;
      if (state.filters.tipos.has(t)) state.filters.tipos.delete(t);
      else state.filters.tipos.add(t);
      btn.classList.toggle('is-active');
      render();
    });
  });
}

function renderInmoDatalist() {
  const dl = document.getElementById('inmoList');
  const names = [...new Set(state.listings.map((l) => l.inmobiliaria).filter(Boolean))].sort();
  dl.innerHTML = names.map((n) => `<option value="${escape(n)}"></option>`).join('');
}

// -------- Filter + sort --------
function matches(l) {
  const f = state.filters;
  if (f.barrios.size && !f.barrios.has(l.barrio)) return false;
  if (f.sources.size && !f.sources.has(l.source)) return false;
  if (f.tipos.size && !f.tipos.has(l.tipo_propiedad || '?')) return false;
  if (f.inmobiliaria) {
    const q = f.inmobiliaria.toLowerCase();
    if (!(l.inmobiliaria || '').toLowerCase().includes(q)) return false;
  }
  const usd = usdOf(l);
  if (f.priceMin != null && (usd == null || usd < f.priceMin)) return false;
  if (f.priceMax != null && (usd == null || usd > f.priceMax)) return false;
  if (f.ambientesMin != null) {
    // si no declara ambientes, usamos dormitorios+1 como proxy
    const amb = l.ambientes ?? (l.dormitorios != null ? l.dormitorios + 1 : null);
    if (amb == null || amb < f.ambientesMin) return false;
  }
  if (f.m2Min > 0) {
    // Si m² es null (muchos temporarios no lo publican), dejamos pasar — no filtramos a ciegas.
    if (l.m2 != null && l.m2 < f.m2Min) return false;
  }
  for (const feat of f.features) {
    if (!l.features?.[feat]) return false;
  }
  if (f.hideComercial && l.features?.solo_comercial) return false;
  return true;
}

function sortListings(arr) {
  const cmp = {
    'price-asc':  (a, b) => (usdOf(a) ?? Infinity) - (usdOf(b) ?? Infinity),
    'price-desc': (a, b) => (usdOf(b) ?? -Infinity) - (usdOf(a) ?? -Infinity),
    'm2-desc':    (a, b) => (b.m2 ?? -Infinity) - (a.m2 ?? -Infinity),
    'amb-desc':   (a, b) => (b.ambientes ?? b.dormitorios ?? -Infinity) - (a.ambientes ?? a.dormitorios ?? -Infinity),
  }[state.sort];
  return [...arr].sort(cmp);
}

// -------- Card render --------
function featChips(listing) {
  const f = listing.features || {};
  const chips = [];
  if (f.pet_friendly) chips.push({ label: '★ Apto mascotas', cls: 'feat--star' });
  if (f.al_fondo)     chips.push({ label: '★ Al fondo', cls: 'feat--fondo' });
  if (f.patio)        chips.push({ label: 'Patio', cls: 'feat--good' });
  if (f.terraza)      chips.push({ label: 'Terraza', cls: 'feat--good' });
  if (f.sin_expensas) chips.push({ label: 'Sin expensas', cls: 'feat--good' });
  if (f.amoblado)     chips.push({ label: 'Amoblado', cls: 'feat--warn' });
  if (f.reciclado)    chips.push({ label: 'Reciclado', cls: 'feat--warn' });
  if (f.solo_comercial) chips.push({ label: 'Solo comercial', cls: 'feat--bad' });
  return chips.map((c) => `<span class="feat ${c.cls}">${c.label}</span>`).join('');
}

function renderCard(l) {
  const initial = (l.barrio || '?').charAt(0).toUpperCase();
  const imgs = l.imagenes || [];
  const firstImg = imgs[0];
  const usd = usdOf(l);
  const usdLabel = usd != null ? `≈ USD ${usd.toLocaleString('es-AR')}` : '';

  const expensas = l.expensas == null ? ''
    : l.expensas === 0 ? '<span class="card__expensas">sin expensas</span>'
    : `<span class="card__expensas">+ exp. ${fmtPrice(l.expensas, 'ARS')}</span>`;

  const periodLabel = l.periodo_label
    || (l.periodo_dias === 30 ? 'mensual'
        : l.periodo_dias === 1 ? 'por noche'
        : l.periodo_dias ? `por ${l.periodo_dias} días`
        : 'mensual');

  const flags =
    (l.features?.pet_friendly ? '<span class="card__flag card__flag--star">★ Apto mascotas</span>' : '') +
    (l.features?.al_fondo ? '<span class="card__flag card__flag--fondo">★ Al fondo</span>' : '');

  const amb = l.ambientes ?? (l.dormitorios != null ? `${l.dormitorios}+1` : null);

  return `
    <a class="card" href="${escape(l.url)}" target="_blank" rel="noopener" data-id="${escape(l.id)}">
      <div class="card__image ${bgClass(l.barrio)}" data-imgs='${escape(JSON.stringify(imgs))}'>
        ${firstImg ? `<img class="card__photo" src="${escape(firstImg)}" alt="${escape(l.titulo)}" loading="lazy" onerror="this.remove()" />` : `<div class="card__icon">${escape(initial)}</div>`}
        ${imgs.length > 1 ? `<div class="card__dots">${imgs.map((_, i) => `<span class="card__dot${i === 0 ? ' is-active' : ''}"></span>`).join('')}</div>` : ''}
        ${flags ? `<div class="card__flags">${flags}</div>` : ''}
        <span class="card__barrio">${escape(l.barrio || '—')}</span>
        <span class="card__source">${escape(l.source)}</span>
      </div>
      <div class="card__body">
        <div class="card__price">
          <span class="card__price-main">${fmtPrice(l.precio, l.moneda)}</span>
          <span class="card__price-period">${escape(periodLabel)}</span>
          ${expensas}
        </div>
        ${usd && (l.periodo_dias !== 30 || l.moneda === 'ARS') ? `<div class="card__price-usd">${usdLabel} /mes equiv. (@${EXCHANGE_RATE} ARS/USD, × 30/${l.periodo_dias || 30})</div>` : ''}
        <div class="card__title">${escape(l.titulo)}</div>
        <div class="card__address">${escape(l.direccion || '')}${l.inmobiliaria ? ` · <span class="card__inmo">${escape(l.inmobiliaria)}</span>` : ''}</div>
        ${(l.also_in_sources && l.also_in_sources.length) ? `<div class="card__also">También en ${l.also_in_sources.map((a) => escape(a.source)).join(', ')}</div>` : ''}
        <div class="card__stats">
          <span><strong>${fmtInt(amb)}</strong> amb</span>
          <span><strong>${fmtInt(l.dormitorios)}</strong> dorm</span>
          <span><strong>${fmtInt(l.m2)}</strong> m²</span>
        </div>
        <div class="card__features">${featChips(l)}</div>
        <div class="card__cta">Ver aviso →</div>
      </div>
    </a>`;
}

function attachCarousels(root) {
  root.querySelectorAll('.card__image').forEach((imgBox) => {
    let imgs = [];
    try { imgs = JSON.parse((imgBox.dataset.imgs || '[]').replace(/&quot;/g, '"')); } catch { /**/ }
    if (imgs.length < 2) return;
    const photo = imgBox.querySelector('.card__photo');
    const dots = imgBox.querySelectorAll('.card__dot');
    if (!photo) return;
    let idx = 0;
    let iv = null;
    const update = (i) => {
      idx = i;
      photo.src = imgs[idx];
      dots.forEach((d, j) => d.classList.toggle('is-active', j === idx));
    };
    imgBox.addEventListener('mouseenter', () => {
      iv = setInterval(() => update((idx + 1) % imgs.length), 800);
    });
    imgBox.addEventListener('mouseleave', () => {
      clearInterval(iv);
      update(0);
    });
  });
}

function render() {
  const filtered = sortListings(state.listings.filter(matches));
  document.getElementById('resultCount').textContent = filtered.length;
  const grid = document.getElementById('grid');
  const empty = document.getElementById('empty');
  if (!filtered.length) {
    grid.innerHTML = '';
    empty.hidden = false;
  } else {
    empty.hidden = true;
    grid.innerHTML = filtered.map(renderCard).join('');
    attachCarousels(grid);
  }
}

// -------- Controls --------
function activateSegmented(containerId, value, attr) {
  document.querySelectorAll(`#${containerId} button`).forEach((b) => {
    b.classList.toggle('is-active', b.dataset[attr] === String(value));
  });
}

function bindControls() {
  document.querySelectorAll('#filterAmbientes button').forEach((b) => {
    b.addEventListener('click', () => {
      activateSegmented('filterAmbientes', b.dataset.amb, 'amb');
      state.filters.ambientesMin = b.dataset.amb === 'ALL' ? null : Number(b.dataset.amb);
      render();
    });
  });
  document.querySelectorAll('#filterM2 button').forEach((b) => {
    b.addEventListener('click', () => {
      activateSegmented('filterM2', b.dataset.m2, 'm2');
      state.filters.m2Min = Number(b.dataset.m2);
      render();
    });
  });
  document.getElementById('priceMin').addEventListener('input', (e) => {
    state.filters.priceMin = e.target.value ? Number(e.target.value) : null;
    render();
  });
  document.getElementById('priceMax').addEventListener('input', (e) => {
    state.filters.priceMax = e.target.value ? Number(e.target.value) : null;
    render();
  });
  document.getElementById('filterInmo').addEventListener('input', (e) => {
    state.filters.inmobiliaria = e.target.value.trim();
    render();
  });
  document.querySelectorAll('input[data-feat]').forEach((el) => {
    el.addEventListener('change', () => {
      const f = el.dataset.feat;
      if (el.checked) state.filters.features.add(f);
      else state.filters.features.delete(f);
      render();
    });
  });
  document.getElementById('hideComercial').addEventListener('change', (e) => {
    state.filters.hideComercial = e.target.checked;
    render();
  });
  document.getElementById('sortBy').addEventListener('change', (e) => {
    state.sort = e.target.value;
    render();
  });
  document.getElementById('resetBtn').addEventListener('click', () => {
    state.filters = {
      barrios: new Set(), sources: new Set(), tipos: new Set(['PH']), inmobiliaria: '',
      priceMin: null, priceMax: null, ambientesMin: 2, m2Min: 50,
      features: new Set(['amoblado']), hideComercial: true,
    };
    document.querySelectorAll('#filterBarrios .chip.is-active, #filterSources .chip.is-active').forEach((x) => x.classList.remove('is-active'));
    document.querySelectorAll('#filterTipos .chip').forEach((x) => {
      x.classList.toggle('is-active', x.dataset.tipo === 'PH');
    });
    activateSegmented('filterAmbientes', '2', 'amb');
    activateSegmented('filterM2', '50', 'm2');
    document.querySelectorAll('input[type="checkbox"]').forEach((x) => {
      x.checked = x.id === 'hideComercial' || x.dataset.feat === 'amoblado';
    });
    document.getElementById('priceMin').value = '';
    document.getElementById('priceMax').value = '';
    document.getElementById('filterInmo').value = '';
    render();
  });
}

(async function main() {
  try {
    await loadData();
    renderBarrioChips();
    renderSourceChips();
    renderTipoChips();
    renderInmoDatalist();
    bindControls();
    render();
  } catch (err) {
    console.error('Failed to init:', err);
    document.getElementById('grid').innerHTML =
      '<p style="padding:40px;color:#8a8277">No se pudo cargar data.json. Corré <code>cd site &amp;&amp; python3 -m http.server 8000</code> y visitá <code>http://localhost:8000</code>.</p>';
  }
})();
