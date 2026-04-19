# Mudanza de Helen a CABA — brief

## Perfil de búsqueda

- Viene de Olivos, valora calma (nada de avenidas ruidosas).
- Dos gatos → necesita patio/terraza o al menos buena ventilación propia.
- Graba música con monitores hasta tarde → aislamiento acústico es crítico.
- Le gusta consumir cultura, bares, restos (Palermo como eje de referencia).

---

## Tipo de vivienda: PH

Depto descartado de entrada — reglamento de copropiedad + ruido estructural por los monitores + vecinos colindantes = incompatible. Casa en CABA es ideal pero carísima y escasa. El punto medio real es **PH**.

### Lo que hay que buscar específicamente

- **PH "al fondo"** (2º o 3º al fondo): sin unidad arriba. Es lo más importante para el tema ruido.
- PH al frente con terraza también puede funcionar, pero hay que chequear vecinos colindantes.
- **Patio o terraza propios** (gatos + aire + ventilación independiente).
- **Construcción antigua**, idealmente años 30-50 (paredes de ladrillo macizo juegan a favor acústicamente).
- **Evitar PHs reciclados a nuevo con tabiques de durlock como medianeras** — son un desastre acústico.

### Checklist para la visita

- Tocar la medianera: si suena hueca = durlock/pladur, descartar.
- Ir a visitar de noche si se puede, para chequear ruido real del barrio.
- Preguntar qué hay arriba y al costado (vivienda, oficina, local comercial).
- Ver si el patio tiene rejas o es escalable (gatos fugitivos).
- Humedad en paredes y techo (los PHs viejos son propensos).
- Estado de la instalación eléctrica (setup de grabación pide tomas decentes).
- Preguntar por el estado del consorcio/vecinos directos (cuánto más chico el consorcio, mejor).

---

## Barrios, por prioridad

**Primera línea — pegados a Palermo, con stock de PHs:**
- **Chacarita**: mucho PH antiguo, gastronomía propia creciendo fuerte (Dorrego, Jorge Newbery). Muy buen balance.
- **Colegiales**: el más calmo de los tres, residencial, muy "Olivos-friendly" en vibra. Mi top recomendación.
- **Villa Crespo**: mejor relación precio/ubicación, gastronomía propia sólida, más movido.

**Segunda línea — un escalón más tranquilo:**
- **Villa Ortúzar**: intermedio bueno, muy residencial, precios más bajos.
- **Parque Chas**: casi un pueblo dentro de CABA, identidad fuerte, ideal para grabar de noche. Puede ser demasiado quieto si viene buscando algo de movimiento.

**Tercera línea — continuidad Olivos + mejor perfil acústico:**
- **Belgrano R / Núñez**: cerca de donde vive ahora, muy residencial, casas bajas, tráfico suave. A 15-20 min de Palermo por Cabildo/Libertador. Oferta cultural propia más acotada (se va a Palermo a consumir), pero **el perfil acústico supera a todo lo de primera/segunda línea** — y para grabar con monitores eso pesa.

**Cuarta línea — Opción B, Palermo:**
- PHs lindos en cuadras internas (Palermo Soho hacia Scalabrini, o Palermo Pacífico entre Santa Fe y Las Heras).
- Pagás premium grande y las zonas más lindas son ruidosas de noche por los bares — justo lo contrario a lo que ella busca.

**Quinta línea — más lejos del eje Palermo pero válidos:**
- **Almagro**: PHs clásicos, más barato, cultura del Abasto, un toque más caótico.
- **Caballito**: muchos PHs, muy tranquilo, pero lejos del circuito gastronómico.
- **Saavedra**: el más residencial de toda la lista, precios más bajos que Belgrano/Núñez, mucho PH con patio. Contrapartida: **el más lejos del eje cultural** (25-30 min a Palermo), oferta gastronómica propia mínima. Vale solo si Helen acepta el pacto *"vivo en silencio, salgo a Palermo cuando quiero movida"*.

---

## Formas de contratación

### Sin residencia (solo pasaporte uruguayo)

| Opción | Evaluación |
|---|---|
| **Airbnb amoblado** | Fricción cero, ideal 1-4 semanas. Caro (dolarizado), pet-friendly escasea, ruido = problema. **Puente inicial para conocer barrios.** |
| **Temporario amoblado 3-6 meses** | Accesible: pasaporte + tarjeta + depósito/adelantos. Más barato que Airbnb, más flexible con mascotas (negociable). **Opción principal pre-residencia.** |
| **Temporario sin amueblar 3-6 meses** | Difícil sin DNI: dueños piden más garantías. Con garante (depto propio) se destraba. **Solo si ya tenés PH definitivo y querés ahorrar.** |
| **Tradicional 3+ años sin amueblar** | Casi descartado: inmobiliarias piden DNI al titular. Algunas flexibles aceptan con precaria en trámite, pero son excepción. **No apuntar acá todavía.** |

### Con residencia (precaria o DNI en mano)

| Opción | Evaluación |
|---|---|
| **Airbnb amoblado** | Solo para estadías muy cortas. Nada cambia, sigue siendo puente. |
| **Temporario amoblado 3-6 meses** | Cómoda si no quieren comprometerse largo. **Si todavía están explorando barrios.** |
| **Temporario sin amueblar 3-6 meses** | Viable: DNI + garante = dueño tranquilo. Buen ahorro vs amoblado. **Si ya tienen muebles/equipo para mudar.** |
| **Tradicional 3+ años sin amueblar** | Camino óptimo económicamente. Con garantía propietaria destrabás todo. **El objetivo final: PH al fondo en Colegiales/Chacarita/Villa Crespo.** |

---

## Sites e inmobiliarias

Lo verificado abril 2026. El site acompañante (site/) scrapea automáticamente los que dicen ✅; los demás son para consulta manual.

### Scrape-ables automáticamente
- ✅ **Argenprop** — buen volumen PH-alquiler por barrio. URL: `/ph/alquiler/{barrio}`.
- ✅ **Remax** — API pública Angular. ~80 listings CABA (PH rent + temporal).
- ✅ **ZonaProp** — el más grande del mercado. Requiere `curl_cffi` para pasar Cloudflare; ~92 PHs. URL: `/ph-alquiler-{barrio1}-{barrio2}.html`.
- ✅ **MercadoLibre Inmuebles** — UI web scrape-able (la API oficial tira 403). ~82 PHs. URL: `/ph/{alquiler|alquiler-temporario}/capital-federal/{barrio-o-barrio}/`.
- ✅ **Airbnb** — parseo de SSR state (niobeClientData). ~120 temporarios. Lumped como `tipo=Depto` en la UI (Airbnb no categoriza PH).

### Bloqueados / no útiles
- ❌ **Properati** — accesible con `curl_cffi` pero no expone PH como tipo (todo "Departamento"). Sin valor agregado vs otras fuentes.
- ❌ **Mudafy** — React SPA, listings se hidratan client-side; cero contenido en HTML inicial. Requeriría headless browser.

### Temporario amoblado (pre-residencia)
Para la etapa pre-residencia (pasaporte, sin DNI) el amoblado es el puente. El brief lo asume. Pero el mercado amoblado en PH es escaso — la mayor parte del stock amoblado son deptos. Si Helen abre el criterio a "depto temporario" pre-residencia:
- **Airbnb / Booking** — catálogo enorme pero casi todo deptos (Airbnb no categoriza "PH" en Argentina). Útil como último recurso; negociar directo con host puede bajar 20-30%.
- **ByT Argentina** (bytargentina.com) — clásico, stock grande. Consulta manual (sitio no scrape-able: SPA).

### Dueño directo / sin inmobiliaria (manual)
- Grupos de Facebook: "Alquileres sin garantía CABA", "Alquileres temporarios Buenos Aires", grupos barriales (Palermo/Chacarita/Colegiales).
- Marketplace de Facebook.

### Inmobiliarias de zona (tradicional, necesita garante)
- **Tizado**, **Remax** — grandes, cobertura amplia. Remax ya está scrape-able (ver arriba).
- Buscar inmobiliarias chicas de barrio en Colegiales / Chacarita / Villa Crespo — suelen ser más flexibles y conocen el stock real de PHs.
- ~~Toribio Achaval~~ — no expone alquileres en la web pública (solo /listado/departamentos/venta/).
- ~~Inmobusqueda~~ — requiere verificación JS (captcha navegador). No scrape-able en abril 2026.

---

## Red flags que descartan una propiedad

- Medianeras de durlock (tabique hueco).
- Vecino de arriba (en PH que no es "al fondo").
- Patio compartido con otros PHs del pasillo.
- Reglamento interno con cláusula de "no ruidos molestos después de las 22h" — común en PHs de consorcio chico.
- Humedad estructural (manchas en techo, descascarado).
- Instalación eléctrica antigua sin actualizar (riesgo para el setup de grabación).
- Dueño que "no quiere problemas con los vecinos" = ya hay historial.

---

## Presupuesto orientativo (a validar en el momento de buscar)

Los precios en CABA se mueven rápido y están parcialmente dolarizados, así que esto es solo para tener una referencia mental — chequear ZonaProp antes de cualquier decisión concreta.

- **PH tradicional 2-3 amb**: rango muy amplio según estado y metros, pero arrancan desde el equivalente a USD 500-700/mes en Chacarita/Villa Crespo, USD 800-1.200 en Palermo/Colegiales bien ubicado.
- **Expensas en PH**: suelen ser bajísimas o cero (ventaja grande vs. depto).
- **Gastos de ingreso**: depósito (1-2 meses) + comisión inmobiliaria + sellado. Calcular ~2-3 meses de alquiler al firmar.
