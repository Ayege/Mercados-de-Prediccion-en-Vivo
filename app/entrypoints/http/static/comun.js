// Utilidades compartidas por la vista de la audiencia y la de proyección.

const TIPOS = {
  presente: {
    etiqueta: "Ya ocurrió",
    mide: "La respuesta ya existe y es verificable. Nadie aquí la sabe con certeza: el precio agrega lo que la sala sabe en conjunto.",
  },
  futuro: {
    etiqueta: "Aún no tiene respuesta",
    mide: "Hoy es irresoluble a propósito. Lo correcto es que el oráculo diga SIN RESOLVER.",
  },
  sala: {
    etiqueta: "Información de la sala",
    mide: "La respuesta está repartida entre ustedes y ningún buscador la tiene. La resuelve un censo privado, no el oráculo.",
  },
  simulacion: {
    etiqueta: "Nube simulada",
    mide: "Nadie sabe qué harán los agentes: el comportamiento es emergente. La resuelve el código de la simulación, no un modelo ni la sala.",
  },
  noticias: {
    etiqueta: "Desde las noticias",
    mide: "Nació de las noticias del día. Cuatro agentes leen la cobertura según su dieta de medios y apuestan aquí; la sala apuesta con ellos. La resuelve el oráculo cuando llegue la fecha del criterio.",
  },
  real: {
    etiqueta: "Nube real · Cloud Run",
    mide: "Se resuelve con lo que pase de verdad en Google Cloud: una falla real, un detector real y una reparación real, cronometrados.",
  },
};

// El tipo que se muestra: las preguntas que resuelve la infraestructura real tienen el suyo.
function tipo(m) {
  if (m.topic) return TIPOS.noticias;
  return TIPOS[m.resolver === "infraestructura real" ? "real" : m.kind];
}

// Las preguntas que nacieron de las noticias van primero, la más reciente arriba.
function ordenar(mercados) {
  const noticias = mercados.filter(m => m.topic).reverse();
  return [...noticias, ...mercados.filter(m => !m.topic)];
}

const RESULTADO = { YES: "SÍ", NO: "NO", UNRESOLVED: "SIN RESOLVER" };

const FALLOS = {
  baja_confianza: "Baja confianza",
  un_dominio: "Un solo dominio",
  json_malformado: "JSON malformado",
  red_caida: "Red caída",
  noticia_como_verdad: "Noticia tomada como verdad",
};

// Preguntas desde las noticias: la dieta de medios de cada agente.
const DIETAS = { izquierda: "solo medios de izquierda", derecha: "solo medios de derecha",
                 ambas: "medios de ambos lados", ninguna: "ningún medio" };

function cobertura(articulos) {
  const lado = l => articulos.filter(a => a.lean === l).map(a => `<li><a href="${esc(a.url)}" rel="noopener noreferrer"
      target="_blank">${esc(a.headline)}</a> <span class="tenue">— ${esc(a.outlet)}${a.via ? ` · vía ${esc(a.via)}` : ""}</span></li>`).join("")
    || `<li class="tenue">sin titulares</li>`;
  return `<div class="cobertura">
    <div><strong class="pequeno lado-izquierda">Izquierda</strong><ul class="pequeno">${lado("izquierda")}</ul></div>
    <div><strong class="pequeno lado-derecha">Derecha</strong><ul class="pequeno">${lado("derecha")}</ul></div>
  </div>`;
}

// Las preguntas con encuadre: dos titulares, cada persona ve uno.
const GRUPOS = { pro_si: "titular pro-SÍ", pro_no: "titular pro-NO" };

function titular(h, etiqueta = "") {
  if (!h) return "";
  const fuente = h.url
    ? `<a href="${esc(h.url)}" rel="noopener noreferrer" target="_blank">${esc(h.source)}</a>` : esc(h.source);
  return `<blockquote class="titular">${etiqueta ? `<span class="pequeno tenue">${esc(etiqueta)}</span><br>` : ""}
    «${esc(h.text)}» <span class="pequeno tenue">— ${fuente}</span></blockquote>`;
}

function esc(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function pct(p) {
  return `${Math.round(p * 100)} %`;
}

async function api(ruta, opciones = {}) {
  const r = await fetch(ruta, opciones);
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) {
    const error = new Error(cuerpo.detail?.[0]?.msg || cuerpo.detail || `error ${r.status}`);
    error.status = r.status;
    throw error;
  }
  return cuerpo;
}

// La clave del ponente viaja en el fragmento (#clave=…), que el navegador no envía al servidor ni a los logs.
const clave = new URLSearchParams(location.hash.slice(1)).get("clave") || "";

function cabeceras(extra = {}) {
  return clave ? { ...extra, "X-Presenter-Key": clave } : extra;
}

// Sin clave en un servidor que la exige, los controles del ponente no se muestran.
const esPonente = info => !(info.presenter_key_required && !clave);

// Sondeo sin solapes y solo con la pestaña visible. Una pestaña olvidada en segundo plano no gasta
// peticiones y, en la nube, deja de contar como «alguien mira»: la vigilia puede apagar los nodos.
function sondear(fn, ms) {
  let espera, enCurso = false;
  async function vuelta() {
    clearTimeout(espera);
    if (enCurso || document.hidden) return;
    enCurso = true;
    try { await fn(); } catch { /* el siguiente sondeo reintenta */ } finally { enCurso = false; }
    if (!document.hidden) espera = setTimeout(vuelta, ms);
  }
  document.addEventListener("visibilitychange", vuelta);
  vuelta();
}

// Solo toca el DOM si el contenido cambió: así un sondeo no cierra un <select> abierto ni roba el foco.
const pintados = new WeakMap();
function pintarSi(el, html) {
  if (pintados.get(el) === html) return;
  pintados.set(el, html);
  el.innerHTML = html;
}

function guardado(clave, valor) {
  try {
    if (valor === undefined) return localStorage.getItem(clave);
    localStorage.setItem(clave, valor);
  } catch { /* sin almacenamiento: la página funciona igual */ }
  return valor;
}

// Línea de precio con referencia en 50 %. `history` guarda P(SÍ) tras cada orden.
function sparkline(historia, ancho = 320, alto = 80) {
  const h = historia.length > 1 ? historia : [historia[0] ?? 0.5, historia[0] ?? 0.5];
  const x = i => (i / (h.length - 1)) * ancho;
  const y = p => alto - p * alto;
  const puntos = h.map((p, i) => `${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
  return `<svg class="spark" viewBox="0 0 ${ancho} ${alto}" preserveAspectRatio="none" role="img"
      aria-label="Evolución del precio del SÍ">
    <line x1="0" x2="${ancho}" y1="${alto / 2}" y2="${alto / 2}" class="spark-ref"/>
    <polyline points="${puntos}" class="spark-linea" vector-effect="non-scaling-stroke"/>
  </svg>`;
}
